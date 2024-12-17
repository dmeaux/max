# ===----------------------------------------------------------------------=== #
# Copyright (c) 2024, Modular Inc. All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions:
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===----------------------------------------------------------------------=== #

from dataclasses import dataclass
from pathlib import Path
from typing import KeysView, Union

import gguf
import numpy as np
from max.dtype import DType
from max.engine import InferenceSession, Model
from max.graph import Graph, TensorType
from max.graph.utils.load_gguf import Weights

from utils import gguf_utils, tokenizer_from_gguf

from .config import InferenceConfig
from .gguf import transformer
from .kv_cache import KVCache
from .model.hyperparameters import Hyperparameters


@dataclass
class Llama3Context:
    """The context for text generation using a Llama 3 model."""

    next_token: np.ndarray
    prompt_size: int
    max_tokens: int
    prompt: str


def _llama_graph(
    batch_size: int, params: Hyperparameters, weights: Weights
) -> Graph:
    cache_type = TensorType(
        DType.float32,
        shape=[
            "start_pos",
            params.n_layers,
            batch_size,
            params.n_kv_heads,
            params.head_dim,
        ],
    )
    tokens_type = TensorType(DType.int64, shape=[batch_size, "seq_len"])

    with Graph(
        "llama3", input_types=[tokens_type, cache_type, cache_type]
    ) as graph:
        model = transformer(graph, params, weights)
        logits, k_update, v_update = model(*graph.inputs)
        graph.output(logits[:, -1], k_update, v_update)
        return graph


class Llama3:
    """The overall interface to the Llama 3 model."""

    config: InferenceConfig
    _model: Model
    _kv_cache: KVCache
    _sessions: dict[str, int]

    def __init__(self, config: InferenceConfig):
        self.config = config

        assert config.weight_path is not None
        gguf_reader = gguf.GGUFReader(config.weight_path)

        params = _read_hyperparameters(gguf_reader)
        self._model = self._load_model(config, params, gguf_reader)
        self._tokenizer = tokenizer_from_gguf(gguf_reader)

        # Work around for older Llama 1/2 GGUFs, where the vocab size may be -1.
        # See https://github.com/ggerganov/llama.cpp/pull/4258.
        if params.vocab_size < 0:
            params.vocab_size = self._tokenizer.vocab_size

        self._kv_cache = KVCache(
            params.seq_len,
            config.batch_size,
            params.n_layers,
            params.n_kv_heads,
            params.head_dim,
        )
        self._sessions = {}

    def _load_model(
        self,
        config: InferenceConfig,
        params: Hyperparameters,
        reader: gguf.GGUFReader,
    ) -> Model:
        session = InferenceSession()
        if serialized_path := config.serialized_model_path:
            print("Loading serialized model from", serialized_path, "...")
            return session.load(serialized_path)
        else:
            graph = _llama_graph(config.batch_size, params, Weights(reader))
            print("Compiling...")
            return session.load(graph)

    def _get_attention_mask(self, n: int):
        mask = np.ones(shape=(1, n)).astype(bool)
        return mask

    async def new_context(self, prompt: str) -> Llama3Context:
        encoded_prompt = self._tokenizer.encode(prompt)
        prompt_size = len(encoded_prompt)
        return Llama3Context(
            next_token=np.array(encoded_prompt).reshape(1, -1),
            prompt_size=prompt_size,
            max_tokens=_max_tokens_to_generate(prompt_size, self.config),
            prompt=prompt,
        )

    async def next_token(
        self, batch: dict[str, Llama3Context]
    ) -> dict[str, str]:
        # Note: assuming a single request.
        assert len(batch) == self.config.batch_size == 1
        request_id, context = next(iter(batch.items()))
        # This feels really contrived, but it's because our KV cache setup
        # just doesn't meaningfully support batch size > 1 yet.
        if request_id not in self._sessions:
            self._sessions[request_id] = 0
            self._kv_cache.sequence_length = 0

        cache = self._kv_cache
        input_names = [t.name for t in self._model.input_metadata]
        output_names = [t.name for t in self._model.output_metadata]
        # TODO (MSDK-844): Remove this when attention masks are harmonized between Mojo and Python graphs.
        if len(input_names) == 4:
            inputs = [
                context.next_token,
                self._get_attention_mask(
                    cache.sequence_length + context.next_token.shape[1]
                ),
                cache.keys_view(),
                cache.values_view(),
            ]
        else:
            inputs = [
                context.next_token,
                cache.keys_view(),
                cache.values_view(),
            ]

        result = self._model.execute(**dict(zip(input_names, inputs)))
        logits, k_cache, v_cache = (result[o] for o in output_names)
        self._kv_cache.update(k_cache, v_cache)

        # TODO: Add a weighted sampler here.
        # Get argmax of the logits of the last token.
        next_token = logits.argmax(axis=-1)[-1]
        context.next_token = next_token.reshape(1, -1)
        decoded_token = self._tokenizer.decode(next_token)
        if decoded_token == self._tokenizer.eos_token:
            return {}
        return {request_id: decoded_token}


def _max_tokens_to_generate(prompt_size: int, config: InferenceConfig) -> int:
    """Returns the max number of tokens to generate (including the prompt)."""
    if config.max_new_tokens < 0:
        return config.max_length
    return min(config.max_new_tokens + prompt_size, config.max_length)


def _read_hyperparameters(reader: gguf.GGUFReader) -> Hyperparameters:
    key_names = {
        "n_layers": "llama.block_count",
        "n_heads": "llama.attention.head_count",
        "n_kv_heads": "llama.attention.head_count_kv",
        "vocab_size": "llama.vocab_size",
        "hidden_dim": "llama.embedding_length",
        "rope_theta": "llama.rope.freq_base",
        "layer_norm_rms_epsilon": "llama.attention.layer_norm_rms_epsilon",
    }

    configured_params = {
        name: value
        for name, key in key_names.items()
        if (value := gguf_utils.read_number(reader, key)) is not None
    }

    return Hyperparameters(**configured_params)

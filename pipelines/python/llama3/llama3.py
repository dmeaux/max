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

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

import gguf
import numpy as np
from max.driver import Tensor, CPU
from max.dtype import DType
from max.engine import InferenceSession, Model
from max.graph import Graph, TensorType
from max.graph.weights import GGUFWeights
from tokenizers import Tokenizer

from utils import gguf_utils, tokenizer_from_gguf
from .config import InferenceConfig, SupportedVersions
from .gguf import transformer
from .kv_cache_params import KVCacheParams
from .kv_cache import KVCache
from .model.hyperparameters import Hyperparameters


class PaddingDirection(Enum):
    """
    Padding (from) direction for attention_mask.
    """

    LEFT = "left"
    RIGHT = "right"

    def __str__(self) -> str:
        return self.value


@dataclass
class Llama3Context:
    """The context for text generation using a Llama 3 model."""

    prompt: str
    max_tokens: int  # Max number of tokens including input.
    next_tokens: np.ndarray = field(default_factory=lambda: np.array([]))
    tokens: list[int] = field(default_factory=list)  # Tokens generated so far.
    decoded: str = ""  # Decoded text sequence from tokens above.

    def append(self, token_ids: np.ndarray, decoded: str):
        assert token_ids.shape[0] == 1 and token_ids.shape[1] >= 1
        self.next_tokens = token_ids
        self.tokens.extend(token_ids[0])
        self.decoded += decoded

    def is_done(self, eos: int) -> bool:
        if self.tokens[-1] == eos:
            return True
        if len(self.tokens) > self.max_tokens:
            return True
        return False


def _llama_graph(
    batch_size: int,
    params: Hyperparameters,
    weights: GGUFWeights,
    kv_params: KVCacheParams,
) -> Graph:
    tokens_type = TensorType(DType.int64, shape=[batch_size, "seq_len"])
    attn_mask_type = TensorType(
        DType.bool,
        shape=[batch_size, params.n_heads, "seq_len", "post_seq_len"],
    )
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

    with Graph(
        "llama3",
        input_types=[tokens_type, attn_mask_type, cache_type, cache_type],
    ) as graph:
        model = transformer(graph, params, weights, kv_params)
        logits, k_update, v_update = model(*graph.inputs)
        graph.output(logits[:, -1], k_update, v_update)
        return graph


class Llama3:
    """The overall interface to the Llama 3 model."""

    config: InferenceConfig
    _model: Model
    _kv_cache: KVCache
    _sessions: set[str]
    _kv_params: KVCacheParams
    _tokenizer: Tokenizer

    def __init__(self, config: InferenceConfig):
        self.config = config

        assert config.weight_path is not None
        gguf_reader = gguf.GGUFReader(config.weight_path)

        params = _read_hyperparameters(config, gguf_reader)

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
        self._sessions = set[str]()

        dtype = (
            DType.float32 if params.quantization_encoding
            is not None else params.dtype
        )
        self._kv_params = KVCacheParams(
            n_kv_heads=params.n_kv_heads,
            head_dim=params.head_dim,
            dtype=dtype,
            device=config.device,
        )

        self._tokenizer = tokenizer_from_gguf(gguf_reader)
        self._model = self._load_model(config, params, gguf_reader)

        self._n_heads = params.n_heads

    def _load_model(
        self,
        config: InferenceConfig,
        params: Hyperparameters,
        reader: gguf.GGUFReader,
    ) -> Model:
        session = InferenceSession(device=config.device)
        if serialized_path := config.serialized_model_path:
            print("Loading serialized model from", serialized_path, "...")
            return session.load(serialized_path)
        else:
            self._weights = GGUFWeights(reader)
            print("Building model...")
            graph = _llama_graph(
                config.batch_size, params, self._weights, self._kv_params
            )
            print("Compiling...")
            return session.load(
                graph, weights_registry=self._weights.allocated_weights
            )

    def _attention_mask(self, batch_size: int, n: int):
        # TODO(MSDK-977): We shouldn't be broadcasting attn_mask across kv_heads
        # and the second copy of n here.
        return np.ones(shape=(batch_size, self._n_heads, n, n)).astype(bool)

    async def new_context(
        self, prompt: str, max_new_tokens: Optional[int] = None
    ) -> Llama3Context:
        encoded_prompt = self._tokenizer.encode(prompt)
        prompt_size = len(encoded_prompt)
        max_tokens_to_generate = _max_tokens_to_generate(
            prompt_size, self.config, max_new_tokens
        )
        context = Llama3Context(
            prompt=prompt, max_tokens=prompt_size + max_tokens_to_generate
        )
        context.append(np.array(encoded_prompt).reshape(1, -1), prompt)
        return context

    async def next_token(
        self, req_to_context_dict: dict[str, Llama3Context]
    ) -> dict[str, str | None]:
        # TODO(MSDK-889) - Consider moving request/cache mgmt out of next_token.

        res = {}
        if self._sessions ^ req_to_context_dict.keys():
            self._sessions = set(req_to_context_dict.keys())
            self._reset_cache()

        req_id_to_logits_dict, _, _ = self._execute(req_to_context_dict)

        for request_id, context in req_to_context_dict.items():
            # TODO: Add a weighted sampler here.
            # Get argmax of the logits of the last token.
            next_token = req_id_to_logits_dict[request_id].argmax(axis=-1)[-1]
            decoded_token = self._tokenizer.decode(next_token)

            # Update context
            context.append(next_token.reshape(1, -1), decoded_token)

            # Add back to dictionary
            if not context.is_done(self._tokenizer.eos_token_id):
                res[request_id] = decoded_token
        return res

    def _reset_cache(self):
        # TODO: This feels really contrived, but it's because our KV
        # cache setup just doesn't meaningfully support batch size > 1 yet.
        self._kv_cache.sequence_length = 0

    # TODO(MSDK-979): We may not need this if we can figure out how to leverage
    # the tokenizer's enable_padding() API. Add unit tests if we decide to still
    # keep this.
    def _batch_tensors_with_padding(
        self,
        batch: dict[str, Llama3Context],
        direction: PaddingDirection = PaddingDirection.LEFT,
        pad_token: int = 0,
    ) -> tuple[np.ndarray, int]:
        """Generates a fixed length padded batch tensor, provided a batch of Llama3Context.
        """

        # Calculate Max Length to Batch
        lengths = [request.next_tokens.shape[1] for request in batch.values()]
        max_length = max(lengths)

        # Create list of tensors, with padding
        tensors = []
        for i, context in enumerate(batch.values()):
            if direction == PaddingDirection.LEFT:
                pad_length = (max_length - lengths[i], 0)
            else:
                pad_length = (0, max_length - lengths[i])

            tensors.append(
                np.pad(
                    context.next_tokens,
                    pad_length,
                    mode="constant",
                    constant_values=pad_token,
                )
            )

        batched_np_tensor = np.stack(tensors)
        # Reshape / squeeze batched np tensor from (batch_size, 1, seq_len) to (batch_size, seq_len)
        batched_np_tensor = batched_np_tensor.squeeze(axis=1)
        return batched_np_tensor, max_length

    def _execute(
        self, req_to_context_dict: dict[str, Llama3Context]
    ) -> Tuple[dict[str, np.ndarray], ...]:
        """Executes the model and returns the raw results."""
        batched_np_tensor, max_length = self._batch_tensors_with_padding(
            req_to_context_dict
        )

        attn_mask = self._attention_mask(
            batched_np_tensor.shape[0],  # batch_size
            self._kv_cache.sequence_length + max_length,
        )

        logits, k_cache, v_cache = self._model.execute(
            Tensor.from_numpy(batched_np_tensor, self.config.device),
            Tensor.from_numpy(attn_mask, self.config.device),
            Tensor.from_numpy(self._kv_cache.keys_view(), self.config.device),
            Tensor.from_numpy(self._kv_cache.values_view(), self.config.device),
        )

        if not self.config.device.is_host:
            logits = logits.copy_to(CPU())
            k_cache = k_cache.copy_to(CPU())
            v_cache = v_cache.copy_to(CPU())

        logits = np.from_dlpack(logits)
        k_cache = np.from_dlpack(k_cache)
        v_cache = np.from_dlpack(v_cache)

        self._kv_cache.update(k_cache, v_cache)

        logits_to_return = {}
        k_cache_to_return = {}
        v_cache_to_return = {}

        # Since req_to_context_dict dict is ordered as it was passed in from the
        # input, we just iterate over the req_ids in that order and assign logits that
        # way.
        curr_index = 0
        for req_id in req_to_context_dict.keys():
            logits_to_return[req_id] = logits[curr_index]
            k_cache_to_return[req_id] = k_cache
            v_cache_to_return[req_id] = v_cache
            curr_index += 1
        return logits_to_return, k_cache_to_return, v_cache_to_return


def _max_tokens_to_generate(
    prompt_size: int,
    config: InferenceConfig,
    max_new_tokens: Optional[int] = None,
) -> int:
    """Returns the max number of tokens to generate (including the prompt)."""
    max_new_tokens = (
        max_new_tokens if max_new_tokens is not None else config.max_new_tokens
    )
    if max_new_tokens < 0:
        return config.max_length - prompt_size
    return min(max_new_tokens, config.max_length - prompt_size)


def _read_hyperparameters(
    config: InferenceConfig, reader: gguf.GGUFReader
) -> Hyperparameters:
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

    # The feed forward length doesn't appear in the pretrained llama checkpoint
    # fields. Obtain the value from the shape of the projection weight.
    tensor = next(
        filter(lambda t: t.name == "blk.0.ffn_down.weight", reader.tensors)
    )
    feed_forward_length = tensor.shape[0]

    seq_len = 128_000 if config.version == SupportedVersions.llama3_1 else 8_000
    if config.max_length > seq_len:
        print(
            "Warning: `max_length` is more than the supported context size"
            f"`max_length` is now set to {seq_len}"
        )
        config.max_length = seq_len
    else:
        seq_len = config.max_length

    return Hyperparameters(
        dtype=config.quantization_encoding.dtype,
        quantization_encoding=config.quantization_encoding.quantization_encoding,
        feed_forward_length=feed_forward_length,
        seq_len=seq_len,
        **configured_params,
    )

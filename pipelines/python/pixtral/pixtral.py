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

from __future__ import annotations
import logging

import numpy as np
from typing import Sequence
from max.graph.weights import SafetensorWeights
from max.pipelines import PipelineModel, ModelOutputs, LogProbabilities
from max.pipelines.kv_cache import (
    KVCacheManager,
    KVCacheParams,
    load_kv_manager,
)
from max.driver import Tensor
from max.engine import InferenceSession, Model
from max.pipelines import TextAndVisionContext

from .model.graph import _build_graph


class PixtralModel(PipelineModel):
    """The overall interface to the Pixtral model."""

    def execute(self, *model_inputs: Tensor) -> tuple[Tensor, ...]:  # type: ignore
        return self.model.execute(*model_inputs, copy_inputs_to_device=False)[0]  # type: ignore

    def prepare_initial_token_inputs(
        self,
        context_batch: list[TextAndVisionContext],  # type: ignore
    ) -> tuple[Tensor, ...]:
        # Input row offset type: ["input_row_offset_len"], UInt32
        input_row_offset = Tensor.from_numpy(
            np.cumsum(
                [0] + [ctx.seq_len for ctx in context_batch],
                dtype=np.uint32,
            )
        ).to(self.pipeline_config.device)

        # Input Ids: ["total_seq_len"], Int64
        # Create a ragged token vector of length: sum(len(t) for t in tokens).
        tokens = np.concatenate([ctx.next_tokens for ctx in context_batch])
        input_ids = Tensor.from_numpy(tokens).to(self.pipeline_config.device)

        # TODO: change this to include batch_size and num_images_in_seq dims.
        pixel_values = Tensor.zeros(
            dtype=self.pipeline_config.dtype, shape=[304, 400, 3]
        )
        return (
            input_ids,
            pixel_values,
            input_row_offset,
        )

    def prepare_next_token_inputs(
        self,
        next_tokens: Tensor,
        prev_model_inputs: tuple[Tensor, ...],
    ) -> tuple[Tensor, ...]:
        raise NotImplementedError("not yet implemented.")

    def compute_log_probabilities(
        self,
        model_inputs: Sequence[Tensor],
        model_outputs: ModelOutputs,
        next_tokens: Tensor,
        batch_top_n: list[int],
        batch_echo: list[bool],
    ) -> list[LogProbabilities | None] | None:
        raise NotImplementedError("not yet implemented.")

    def _get_kv_params(self) -> KVCacheParams:
        return KVCacheParams(
            dtype=self.pipeline_config.dtype,
            n_kv_heads=self.pipeline_config.huggingface_config.text_config.num_key_value_heads,
            head_dim=self.pipeline_config.huggingface_config.text_config.head_dim,
            cache_strategy=self.pipeline_config.cache_strategy,
        )

    def load_kv_manager(self, session: InferenceSession) -> KVCacheManager:
        return load_kv_manager(
            params=self._get_kv_params(),
            max_cache_batch_size=self.pipeline_config.max_cache_batch_size,
            max_seq_len=self.pipeline_config.huggingface_config.image_seq_length,  # TODO: verify this
            num_layers=self.pipeline_config.huggingface_config.text_config.num_hidden_layers,
            devices=[self.pipeline_config.device],
            session=session,
        )

    def load_model(self, session: InferenceSession) -> Model:
        if self.pipeline_config.enable_echo:
            msg = "Pixtral model does not currently implement enable echo."
            raise ValueError(msg)

        # Pre-allocate a buffer for input_row_offset in multistep execution.
        # We do this to avoid materializing and copying a buffer with each multistep step
        self._input_row_offset_prealloc = Tensor.from_numpy(
            np.arange(
                self.pipeline_config.max_cache_batch_size + 1, dtype=np.uint32
            )
        ).to(self.pipeline_config.device)

        self._weights = self.pipeline_config.load_weights()

        if not isinstance(self._weights, SafetensorWeights):
            msg = (
                "only safetensors weights are currently supported in Pixtral"
                " models."
            )
            raise ValueError(msg)

        if serialized_path := self.pipeline_config.serialized_model_path:
            # Hydrate all weights to be referenced by the serialized graph.
            weights_registry = {}
            for (
                name,
                tensor,
            ) in self.pipeline_config._tensors.items():  # type:ignore
                weights_registry[name] = tensor.data
            logging.info(
                "Loading serialized model from ", serialized_path, "..."
            )
            return session.load(
                serialized_path,
                weights_registry=weights_registry,
            )
        else:
            logging.info("Building model...")
            graph = _build_graph(
                self.pipeline_config,
                self._weights,
                self._get_kv_params(),
                self.kv_manager,
            )
            logging.info("Compiling...")
            return session.load(
                graph,
                weights_registry=self._weights.allocated_weights,  # type:ignore
            )

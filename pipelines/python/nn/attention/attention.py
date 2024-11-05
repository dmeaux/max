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
"""A vanilla opaque KV Cache optimized attention mechanism."""

from dataclasses import dataclass

from max.graph import TensorValue, ops
from max.pipelines.kv_cache import (
    ContinuousBatchingKVCacheCollection,
    ContinuousBatchingKVCacheCollectionType,
)

from ..kernels import flash_attention, fused_qkv_matmul
from .interfaces import AttentionImpl


@dataclass
class Attention(AttentionImpl):
    def __call__(
        self,
        x: TensorValue,
        kv_collection: ContinuousBatchingKVCacheCollectionType,
        **kwargs,
    ) -> tuple[TensorValue, ContinuousBatchingKVCacheCollection]:
        if "attention_mask" not in kwargs:
            raise ValueError("attn_mask not passed as input to Attention")

        # Get attributes from inputs
        batch_size, seq_len = x.shape[0], x.shape[1]

        # Call into fused qkv matmul.
        xq = fused_qkv_matmul(
            self.kv_params,
            input=x,
            wqkv=self.wqkv,
            kv_collection=kv_collection,
            layer_idx=self.layer_idx,
            n_heads=self.n_heads,
        )

        xq = ops.reshape(
            xq,
            [
                batch_size,
                seq_len,
                self.n_heads,
                self.kv_params.head_dim,
            ],
        )

        # Calculate Flash Attention
        attn_out = flash_attention(
            self.kv_params,
            input=xq,
            kv_collection=kv_collection,
            layer_idx=self.layer_idx,
            attention_mask=kwargs["attention_mask"],
            valid_lengths=kwargs["valid_lengths"],
        )

        attn_out = ops.reshape(attn_out, shape=[batch_size, seq_len, -1])

        return self.wo(attn_out), kv_collection
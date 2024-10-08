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
"""An Opaque KV Cache Optimized attention mechanism."""

from dataclasses import dataclass

from max.dtype import DType
from max.graph import TensorValue, ValueLike, ops
from max.graph.type import Dim, DimLike

from .kernels import (
    flash_attention,
    fused_qk_rope,
    fused_qkv_matmul,
)
from .kv_cache import ContiguousKVCache, KVCacheParams
from .layer import Layer
from .mlp import Linear
from .rotary_embedding import OptimizedRotaryEmbedding


def _dim_to_scalar(dim: Dim) -> TensorValue:
    return ops.shape_to_tensor((dim,)).reshape(())


@dataclass
class OptimizedAttention(Layer):
    n_heads: int
    kv_params: KVCacheParams

    wqkv: TensorValue
    wo: Linear

    # This class will not use the RotaryEmbedding to
    # calculate rope, but it already includes a freqs_cis
    # calculation, which we will borrow
    rope: OptimizedRotaryEmbedding

    def __call__(
        self,
        x: TensorValue,
        attn_mask: ValueLike,
        k_cache: ContiguousKVCache,
        v_cache: ContiguousKVCache,
        valid_lengths: TensorValue,
    ) -> tuple[TensorValue, ContiguousKVCache, ContiguousKVCache]:
        # Get attributes from input.
        batch_size, seq_len = x.shape[0], x.shape[1]

        # Call into fused qkv matmul.
        xq = fused_qkv_matmul(
            self.kv_params,
            input=x,
            wqkv=self.wqkv,
            k_cache=k_cache,
            v_cache=v_cache,
        )

        # Apply rope.
        xq = ops.reshape(
            xq,
            [
                batch_size,
                seq_len,
                self.n_heads,
                self.kv_params.head_dim,
            ],
        )

        # Cast freqs_cis to xq's dtype to match the fused_qk_rope kernel.
        freqs_cis = ops.cast(self.rope.freqs_cis, xq.dtype)

        xq = fused_qk_rope(self.kv_params, xq, k_cache, freqs_cis)

        # Calculate Flash Attention.
        attn_out = flash_attention(
            self.kv_params,
            input=xq,
            k_cache=k_cache,
            v_cache=v_cache,
            attn_mask=attn_mask,
            valid_lengths=valid_lengths,
        )

        attn_out = ops.reshape(attn_out, shape=[batch_size, seq_len, -1])

        return self.wo(attn_out), k_cache, v_cache

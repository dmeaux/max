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
"""All configurable parameters for Llama3."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Union

from max.dtype import DType
from max.graph.quantization import QuantizationEncoding
from nn.kv_cache import KVCacheStrategy


class SupportedVersions(str, Enum):
    llama3 = "3"
    llama3_1 = "3.1"

    def __repr__(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


class SupportedEncodings(str, Enum):
    float32 = "float32"
    bfloat16 = "bfloat16"
    q4_0 = "q4_0"
    q4_k = "q4_k"
    q6_k = "q6_k"

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name

    @property
    def quantization_encoding(self) -> Optional[QuantizationEncoding]:
        return _ENCODING_TO_QUANTIZATION_ENCODING.get(self)

    @property
    def dtype(self) -> DType:
        return _ENCODING_TO_DTYPE[self]

    def hf_model_name(self, version: SupportedVersions) -> str:
        if version == SupportedVersions.llama3:
            return _ENCODING_TO_MODEL_NAME_LLAMA3[self]
        elif version == SupportedVersions.llama3_1:
            return _ENCODING_TO_MODEL_NAME_LLAMA3_1[self]
        else:
            raise ValueError(f"Unsupported version: {version}")


_ENCODING_TO_QUANTIZATION_ENCODING = {
    SupportedEncodings.q4_0: QuantizationEncoding.Q4_0,
    SupportedEncodings.q4_k: QuantizationEncoding.Q4_K,
    SupportedEncodings.q6_k: QuantizationEncoding.Q6_K,
}

_ENCODING_TO_DTYPE = {
    SupportedEncodings.float32: DType.float32,
    SupportedEncodings.bfloat16: DType.bfloat16,
    SupportedEncodings.q4_0: DType.uint8,
    SupportedEncodings.q4_k: DType.uint8,
    SupportedEncodings.q6_k: DType.uint8,
}

_ENCODING_TO_MODEL_NAME_LLAMA3 = {
    SupportedEncodings.float32: "llama-3-8b-f32.gguf",
    SupportedEncodings.bfloat16: "llama-3-8b-instruct-bf16.gguf",
    SupportedEncodings.q4_0: "llama-3-8b-instruct-q4_0.gguf",
    SupportedEncodings.q4_k: "llama-3-8b-instruct-q4_k_m.gguf",
    SupportedEncodings.q6_k: "llama-3-8b-instruct-q6_k.gguf",
}

_ENCODING_TO_MODEL_NAME_LLAMA3_1 = {
    SupportedEncodings.float32: "llama-3.1-8b-instruct-f32.gguf",
    SupportedEncodings.bfloat16: "llama-3.1-8b-instruct-bf16.gguf",
    SupportedEncodings.q4_0: "llama-3.1-8b-instruct-q4_0.gguf",
    SupportedEncodings.q4_k: "llama-3.1-8b-instruct-q4_k_m.gguf",
    SupportedEncodings.q6_k: "llama-3.1-8b-instruct-q6_k.gguf",
}


@dataclass(frozen=True)
class DeviceSpec:
    id: int
    """Provided id for this device."""

    device_type: Literal["cpu", "cuda"] = "cpu"
    """Type of specified device."""

    @staticmethod
    def cpu(id: int = -1):
        return DeviceSpec(id, "cpu")

    @staticmethod
    def cuda(id: int = -1):
        return DeviceSpec(id, "cuda")


@dataclass
class InferenceConfig:
    device_spec: DeviceSpec = DeviceSpec.cpu()
    """Device to run inference upon."""

    weight_path: Optional[Union[str, Path]] = None
    """Path or URL of the model weights."""

    huggingface_weights: Optional[str] = None
    """Hugging Face weights to download and use with this model."""

    version: SupportedVersions = SupportedVersions.llama3_1
    """Llama version."""

    quantization_encoding: SupportedEncodings = SupportedEncodings.q4_k
    """Quantization encoding type."""

    serialized_model_path: Optional[Union[str, Path]] = None
    """If specified, tries to load a serialized model from this path."""

    save_to_serialized_model_path: Optional[Union[str, Path]] = None
    """If specified, tries to save a serialized model to this path."""

    max_length: int = 512
    """Controls the maximum length of the text sequence (includes the input tokens)."""

    max_new_tokens: int = -1
    """Controls the maximum length of the text sequence (does not include the input tokens)."""

    n_duplicate: int = 1
    """Broadcast the static prompt `n_duplicate` times to test batching."""
    # TODO: MSDK-1095 Remove temporary `n_duplicate` cli flag.

    max_cache_batch_size: int = 16
    """Maximum cache size of sequences to the model."""

    cache_strategy: KVCacheStrategy = KVCacheStrategy.CONTINUOUS
    """Force using a specific KV cache strategy, 'naive', 'contiguous' or 'continuous'."""

    pad_to_multiple_of: int = 2
    """Pad input tensors to be a multiple of value provided."""

    top_k: Optional[int] = None
    """Limits the sampling to the K most probable tokens."""

    def __post_init__(self) -> None:
        # Ensure quantization_encoding and kv cache strategy is consistent.
        # If a quantizated encoding is provided, we must use the naive strategy.
        if self.quantization_encoding not in [
            SupportedEncodings.float32,
            SupportedEncodings.bfloat16,
        ]:
            self.cache_strategy = KVCacheStrategy.NAIVE

    @staticmethod
    def help():
        return {
            "weight_path": (
                "Path or URL of the model weights. If not provided, default"
                " weights will be downloaded based on the version and"
                " quantization encoding."
            ),
            "huggingface_weights": (
                "Hugging Face weights to download and use with this model, of"
                " the format [author/repository/file]. For example,"
                " modularai/llama-3.1/llama-3.1-8b-instruct-q4_k_m.gguf"
            ),
            "version": "Llama version.",
            "quantization_encoding": (
                "The encoding to use for a datatype that can be quantized to a"
                " low bits per weight format."
            ),
            "max_length": (
                "Controls the maximum length of the text sequence (includes the"
                " input tokens)."
            ),
            "max_new_tokens": (
                "Controls the maximum length of the text sequence (does not"
                " include the input tokens)."
            ),
            "max_cache_batch_size": "Maximum size of sequences kept in cache.",
            "cache_strategy": (
                "Controls the batching strategy: naive, contiguous or"
                " continuous"
            ),
            "top_k": "Limits the sampling to the K most probable tokens.",
        }

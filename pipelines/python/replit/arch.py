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

from .model import ReplitModel
from max.pipelines import (
    HuggingFaceFile,
    SupportedArchitecture,
    SupportedVersion,
    SupportedEncoding,
    TextTokenizer,
)
from max.pipelines.kv_cache import KVCacheStrategy

replit_arch = SupportedArchitecture(
    name="MPTForCausalLM",
    versions=[
        SupportedVersion(
            name="1.5",
            encodings={
                SupportedEncoding.float32: (
                    HuggingFaceFile(
                        "modularai/replit-code-1.5",
                        "replit-code-v1_5-3b-f32.gguf",
                    ),
                    [KVCacheStrategy.CONTINUOUS],
                ),
                SupportedEncoding.bfloat16: (
                    HuggingFaceFile(
                        "modularai/replit-code-1.5",
                        "replit-code-v1_5-3b-bf16.gguf",
                    ),
                    [KVCacheStrategy.CONTINUOUS],
                ),
            },
            default_encoding=SupportedEncoding.float32,
        )
    ],
    default_version="1.5",
    pipeline_model=ReplitModel,
    tokenizer=TextTokenizer,
)

# DeepSeek Coder V1.5

**Language:** Python

**API**: MAX Graph

This pipeline provides optimized support for the DeepSeek Coder V1.5 code
completion model, a member of the `LlamaForCausalLM` architecture family.
The model itself has been constructed in Python
using the [MAX Graph API](https://docs.modular.com/engine/graph).

The MAX Graph API provides an accessible interface to the construction of
flexible accelerated compute graphs, which are then optimized by the MAX
Engine's advanced graph compiler. This pipeline showcases how a large language
model can be fully defined using Python and MAX Graphs and then compiled for
optimal inference performance via the MAX Engine.

## Model

[DeepSeek Coder](https://github.com/deepseek-ai/DeepSeek-Coder) is an open
source code generation model released by DeepSeek. The core architecture of the
V1.5 version of the model is based on the `LlamaForCausalLM` base large
language model architecture.

## Usage

The easiest way to try out this pipeline is with our Magic command-line tool.

1. Install Magic on macOS and Ubuntu with this command:

   ```shell
   curl -ssL https://magic.modular.com | bash
   ```

   Then run the source command that's printed in your terminal.

   To see the available commands, you can run `magic --help`.
   [Learn more about Magic here](https://docs.modular.com/magic).

2. Clone the MAX examples repository:

   If you don't already have a local clone of this repository, create one via:

   ```shell
   git clone https://github.com/modularml/max.git
   ```

   The following instructions assume that you're present within this pipeline's
   directory, and you can change to it after cloning:

   ```shell
   cd max/pipelines/python/
   ```

3. Host a code generation completion endpoint via MAX Serve.

   MAX Serve provides functionality to host performant OpenAI compatible
   endpoints using the FastAPI framework.

   You can configure the pipeline to be hosted by using the `serve` command.
   For example:

   ```shell
   magic run serve --huggingface-repo-id deepseek-ai/deepseek-coder-7b-instruct-v1.5
   ```

   A request can be submitted via a cURL command.

   ```shell
   curl -N http://localhost:8000/v1/chat/completions \
   -H "Content-Type: application/json" \
   -d '{
       "model": "deepseek-ai/deepseek-coder-7b-instruct-v1.5",
       "stream": true,
       "messages": [
           {"role": "system", "content": "You are a helpful assistant."},
           {"role": "user", "content": "Please complete the following Python function: `def fibonacci(n):`"}
       ]
   }'
   ```

## Options

The following command-line options are available to customize operation of the
pipeline:

- `--huggingface-repo-id`: Specify the repository ID of a Hugging Face model
  repository to use. This is used to load tokenizers, architectures and model
  weights.
- `--force-download`: Specify whether to force a download of configuration
  files and weights even if they already exist in the local cache. Set this
  if you want to ensure you have the correct version of the model.
- `--max-cache-batch-size`: Specifies the maximum batch size to be used.
  Default is 1.
- `--max-ce-batch-size`: Set the maximum cache size reserved for a single
  context encoding batch. The effective limit will be the lesser of this value
  and `max-cache-batch-size`.
  Default is 32.
- `--max-length`: Controls the maximum length of the text sequence
  (includes the input tokens).
  (Default value: 512)
- `--max-new-tokens`: The maximum number of new tokens to generate. If a -1
  value is provided, the model will continue to generate tokens for the entire
  context length. (Default value: -1)
- `--quantization-encoding`: The encoding to use for a datatype that can be
  quantized to a low bits per weight format.
  Valid values: `q4_0`, `q4_k`, `q6_k`, `bfloat16`, `float32`.
  (Default value: `bfloat16`).
- `--save-to-serialized-model-path`: If specified, writes the serialized model
  to this path.
- `--serialized-model-path`: If specified, tries to load a serialized model
  from this path.
- `--top-k`: Limits the sampling to the K most probable tokens. Default is 1.
- `--trust-remote-code`: Indicate whether to allow custom modeling files from
  Hugging Face repositories. Set this to true with caution, as it may
  introduce security risks.
- `--use-gpu`: Uses the GPU to execute the model. A device ID can optionally
  be provided to execute on a specific GPU in the system.
- `--weight-path`: Overrides the default URL, and allows for an
  already-downloaded pretrained weight file to be used with the model.
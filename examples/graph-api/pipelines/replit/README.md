# Replit Code V1.5 3B

**Language:** Mojo 🔥

**API**: MAX Graph

This pipeline demonstrates code completion from an initial prompt using
Replit's Code V1.5 3B large language model. The model itself has been
constructed from end to end in
[the Mojo language](https://docs.modular.com/mojo/) using the
[MAX Graph API](https://docs.modular.com/max/graph).

The MAX Graph API provides an accessible Mojo interface to the construction of
flexible accelerated compute graphs, which are then optimized by the MAX
Engine's advanced graph compiler. This pipeline showcases how a large language
model can be fully defined using Mojo and MAX Graphs and then compiled for
optimal inference performance via the MAX Engine.

## Model

[Replit Code](https://blog.replit.com/replit-code-v1_5) is an open source code
generation model trained on permissively licensed code and released by
[Replit](https://replit.com). The V1.5, 3B variant is the basis for this
implementation, and weights are
[obtained via Hugging Face](https://huggingface.co/replit/replit-code-v1-3b).

## Usage

1. Install MAX:

   If MAX is not already installed, follow
   [the installation instructions](https://docs.modular.com/max/install)
   to set it up on your system.

2. Clone the MAX examples repository:

   If you don't already have a local clone of this repository, create one via:

   ```shell
   git clone https://github.com/modularml/max.git
   ```

   The following instructions assume that you're present within this pipeline's
   directory, and you can change to it after cloning:

   ```shell
   cd max/examples/graph-api/pipelines/replit/
   ```

3. Install Python dependencies:

   You'll need numpy and the Transformers library as we will be using its tokenizers.
   You can do this by running:

   ```shell
   pip install numpy transformers
   ```

4. Run the code completion demo:

   On first execution, the model weights will be downloaded and placed in a
   local `.cache/` directory in your current path. The model will then be
   compiled and code completion will begin from the specified prompt.

   All of the pipelines have been configured to use a common driver, located
   in the directory hosting all MAX Graph examples. Assuming you're starting
   at the path of this README, the command invocation will look like:

   ```shell
   mojo ../../run_pipeline.🔥 replit --prompt 'def hello():\n  print("hello world")'
   ```

## Options

The following command-line options are available to customize operation of the
pipeline:

- `--model-path`: Overrides the default model weights, and allows for an
  already-downloaded pretrained weight file to be used with the model.
- `--prompt`: The text prompt to use for further code generation.
- `--max-length`: An optional token generation configuration to specify maximum
   sequence length.
- `--max-new-tokens`: An optional token generation configuration to specify
   maximum number of tokens.
- `--quantization-encoding`: The encoding to use for a datatype that can be
   quantized to a low bits per weight format. The options for quantized formats
   will download and cache default weights.
- `--warmup-pipeline`: Performs a warmup run of the pipeline before text
   generation.

## Ideas for future extension

This isn't an exhaustive list, but here are some ideas for ways in which this
pipeline may be extended or improved:

- Replace the SentencePiece tokenizer with one written in Mojo. Currently,
the tokenizer is loaded from the `transformers` library via Python
interoperability and it might be useful to have this all in Mojo.
- Incorporate 4-bit quantization.
- Improve the quality of the code generation.
- Identify performance bottlenecks and further tune time-to-first-token and
throughput.

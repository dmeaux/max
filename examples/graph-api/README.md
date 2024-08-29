# MAX Graph API examples

These examples demonstrate the flexibility of the
[MAX Graph API](https://docs.modular.com/max/graph/), a
[Mojo](https://docs.modular.com/mojo/) interface to the advanced graph compiler
within MAX.

## [MAX Pipelines](pipelines/)

End-to-end pipelines that demonstrate the power of
[MAX](https://docs.modular.com/max/) for accelerating common AI workloads, and
more.

We created a common Mojo driver file to execute these pipelines and you can
use it to execute the pipelines as follows.

### Magic instructions

If you have [`magic`](https://docs.modular.com/magic), you can run the
following commands:

```sh
magic run llama2 --prompt "what is the meaning of life"
magic run llama3 --prompt "what is the meaning of life"
magic run quantize-tinystories --prompt "what is the meaning of life"
magic run replit --prompt "what is the meaning of life"
magic run basic
magic run mojo run_pipeline.🔥 [pipeline] [options]
```

### Conda instructions

```sh
# Create a Conda environment if you don't have one
conda create -n max-repo
# Update the environment with the environment.yml file
conda env update -n max-repo -f environment.yml --prune
# Run the example
conda activate max-repo

mojo run_pipeline.🔥 [pipeline] [options] mojo run_pipeline.🔥 [pipeline] [options]

conda deactivate
```

```shell
mojo run_pipeline.🔥 [pipeline] [options]
```

Explore each specific pipeline and follow the detailed instructions provided
in their README files within the [pipelines](./pipelines/) sub-repository.

## [Graph API introduction](basics/)

A basic Mojo Graph API example that provides an introduction to how to
stage and run a computational graph on MAX, following the
[getting started guide](https://docs.modular.com/max/graph/get-started).

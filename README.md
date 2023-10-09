# Morph Code Index

```
# Install from source

git clone https://github.com/morph-labs/mci.git

# install `morph`
cd mci && pip install -e . # set up virtualenv beforehand as needed

cd $REPO_TO_SEARCH # ensure OPENAI_API_KEY is set

morph index .

morph search $YOUR_SEARCH
```

Part of the infrastructure for [Rift](https://www.github.com/morph-labs/rift), the AI-native language server for your personal AI SWE.

## Find relevant code faster

```bash
morph index .
morph search "methods used for checkout and account balance"

...
```

## Make your coding assistants smarter

```python
from mci.ir.index import Index

index = ...

search_results = "\n---\n".join(
    str(index.search("methods used for checkout and account balance"))
)

... # give context to a coding assistant before making a request
```

## Generate training data for your personal SWE

(coming soon)

```python
from mci.ir.index import Index

index = ...

import jsonlines as jsl

with jsl.open("datapoints.jsonl", "w") as f:
    for datapoint in index.generate_data(format="fist", subsample_frac=0.7):
        f.write(datapoint)
```

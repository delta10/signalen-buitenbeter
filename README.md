# Signalen BuitenBeter

[![stability-wip](https://img.shields.io/badge/stability-wip-lightgrey.svg)](https://github.com/mkenney/software-guides/blob/master/STABILITY-BADGES.md#work-in-progress)

This microservice accepts SOAP/XML requests from [BuitenBeter](https://www.buitenbeter.nl/) and translates them to the corresponding [Signalen](https://signalen.org/) API calls.

## Run a development environment

Install the prerequisites with:

```bash
pip3 install -r requirements.txt
```

Then run a watch server with:

```bash
FLASK_APP=server FLASK_ENV=development flask run
```

---
type: source
repo: vinta/awesome-python
url: https://github.com/vinta/awesome-python
---

# vinta/awesome-python

The definitive list that answers "I want to do X in Python, which tool should I use?"

GitHub: https://github.com/vinta/awesome-python

## README

# [Awesome Python](https://awesome-python.com/)

An opinionated guide to the best Python frameworks, libraries, and tools.

**Visit the [website](https://awesome-python.com/) to search and filter projects more easily.**

## **Sponsors**

> The **#10 most-starred repo on GitHub**. Put your product in front of Python developers. [Become a sponsor](SPONSORSHIP.md).

## Categories

**AI & ML**

- [AI and Agents](#ai-and-agents)
- [Deep Learning](#deep-learning)
- [Machine Learning](#machine-learning)
- [Natural Language Processing](#natural-language-processing)
- [Computer Vision](#computer-vision)
- [Recommender Systems](#recommender-systems)

**Web Development**

- [Web Frameworks](#web-frameworks)
- [Web APIs](#web-apis)
- [Web Servers](#web-servers)
- [WebSocket](#websocket)
- [Template Engines](#template-engines)
- [Web Asset Management](#web-asset-management)
- [Authentication](#authentication)
- [Admin Panels](#admin-panels)
- [CMS](#cms)
- [ERP](#erp)
- [Static Site Generators](#static-site-generators)

**HTTP & Scraping**

- [HTTP Clients](#http-clients)
- [Web Scraping](#web-scraping)
- [Email](#email)

**Database & Storage**

- [ORM](#orm)
- [Database Drivers](#database-drivers)
- [Database](#database)
- [Caching](#caching)
- [Search](#search)
- [Serialization](#serialization)

**Data & Science**

- [Data Analysis](#data-analysis)
- [Data Ingestion / ETL](#data-ingestion--etl)
- [Data Validation](#data-validation)
- [Data Visualization](#data-visualization)
- [Geolocation](#geolocation)
- [Science](#science)
- [Quantum Computing](#quantum-computing)

**Developer Tools**

- [Algorithms and Design Patterns](#algorithms-and-design-patterns)
- [Interactive Interpreter](#interactive-interpreter)
- [Code Analysis](#code-analysis)
- [Testing](#testing)
- [Debugging Tools](#debugging-tools)
- [Build Tools](#build-tools)
- [Documentation](#documentation)

**DevOps**

- [DevOps Tools](#devops-tools)
- [Distributed Computing](#distributed-computing)
- [Task Queues](#task-queues)
- [Messaging](#messaging)
- [Job Schedulers](#job-schedulers)
- [Logging](#logging)
- [Network Virtualization](#network-virtualization)

**CLI & GUI**

- [CLI Development](#cli-development)
- [CLI Tools](#cli-tools)
- [GUI Development](#gui-development)

**Text & Documents**

- [Text Processing](#text-processing)
- [HTML Manipulation](#html-manipulation)
- [File Format Processing](#file-format-processing)
- [File Manipulation](#file-manipulation)

**Media**

- [Image Processing](#image-processing)
- [Audio & Video Processing](#audio--video-processing)
- [Game Development](#game-development)

**Python Language**

- [Implementations](#implementations)
- [Built-in Classes Enhancement](#built-in-classes-enhancement)
- [Functional Programming](#functional-programming)
- [Asynchronous Programming](#asynchronous-programming)
- [Date and Time](#date-and-time)

**Python Toolchain**

- [Environment Management](#environment-management)
- [Package Management](#package-management)
- [Package Repositories](#package-repositories)
- [Distribution](#distribution)
- [Configuration Files](#configuration-files)

**Security**

- [Cryptography](#cryptography)
- [Penetration Testing](#penetration-testing)
- [Supply Chain Security](#supply-chain-security)
- [Web Security](#web-security)

**Other**

- [Hardware](#hardware)
- [Microsoft Windows](#microsoft-windows)
- [Miscellaneous](#miscellaneous)

## Projects

**AI & ML**

### AI and Agents

_Libraries for building AI applications, LLM integrations, and autonomous agents._

- Agent Skills
  - [django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) - Django backend agent skills for Django, DRF, Celery, and Django-specific code review.
  - [sentry-skills](https://github.com/getsentry/skills) - Python-focused engineering skills for code review, debugging, and backend workflows.
  - [trailofbits-skills](https://github.com/trailofbits/skills) - Python-friendly security skills for auditing, testing, and safer backend development.
- Orchestration
  - [langchain](https://github.com/langchain-ai/langchain) - Building applications with LLMs through composability.
  - [langgraph](https://github.com/langchain-ai/langgraph) - Low-level orchestration framework for building stateful, long-running LLM agents.
  - [crewai](https://github.com/crewAIInc/crewAI) - A framework for orchestrating role-playing autonomous AI agents for collaborative task solving.
  - [pydantic-ai](https://github.com/pydantic/pydantic-ai) - A Python agent framework for building generative AI applications with structured schemas.
- Vendor Agent SDKs
  - [openai-agents](https://github.com/openai/openai-agents-python) - OpenAI's framework for building and managing AI agents.
  - [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) - Anthropic's Python SDK for building AI agents on Claude Code's harness — custom tools, in-process MCP servers, hooks.
- Personal Assistants
  - [hermes-agent](https://github.com/nousresearch/hermes-agent) - An adaptive personal AI assistant that grows with you.
- Prompt Optimization
  - [dspy](https://github.com/stanfordnlp/dspy) - A framework for programming, not prompting, language models.
- Data Layer
  - [instructor](https://github.com/567-labs/instructor) - A library for extracting structured data from LLMs, powered by Pydantic.
  - [llama-index](https://github.com/run-llama/llama_index) - A data framework for your LLM application.
  - [mem0](https://github.com/mem0ai/mem0) - An intelligent memory layer for AI agents enabling personalized interactions.
- Pre-trained Models
  - [transformers](https://github.com/huggingface/transformers) - A framework that lets you easily use pre-trained transformer models for NLP, vision, and audio tasks.
- LLM Inference and Serving
  - [sglang](https://github.com/sgl-project/sglang) - A high-performance serving framework for large language models and multimodal models.
  - [vllm](https://github.com/vllm-project/vllm) - A high-throughput and memory-efficient inference and serving engine for LLMs.
  - [mlx-lm](https://github.com/ml-explore/mlx-lm) - Run and fine-tune large language models on Apple Silicon with MLX.
- LLM Gateways
  - [LiteLLM](https://github.com/BerriAI/litellm) - Call 100+ LLMs using OpenAI format.
- Image and Video Generation
  - [diffusers](https://github.com/huggingface/diffusers) - A library that provides pre-trained diffusion models for generating and editing images, audio, and video.
- Fine-tuning
  - [unsloth](https://github.com/unslothai/unsloth) - A library for faster LLM fine-tuning and training with reduced memory usage.
- Speech
  - [openai-whisper](https://github.com/openai/whisper) - A general-purpose automatic speech recognition model trained on 680k hours of multilingual and multitask supervised data.
  - [funasr](https://github.com/modelscope/FunASR) - Industrial-grade speech recognition toolkit with 170x realtime speed, 50+ languages, speaker diarization, and emotion detection.
  - [vibevoice](https://github.com/microsoft/VibeVoice) - A family of open-source voice AI models from Microsoft for text-to-speech and long-form speech recognition.
  - [gTTS](https://github.com/pndurette/gTTS) - Python library and CLI tool for converting text to speech using Google Translate TTS.
  - [kittentts](https://github.com/KittenML/KittenTTS) - Lightweight ONNX text-to-speech library with small CPU-friendly models.

### Deep Learning

_Frameworks for Neural Networks and Deep Learning. Also see [awesome-deep-learning](https://github.com/ChristosChristofidis/awesome-deep-learning)._

- Frameworks
  - [pytorch](https://github.com/pytorch/pytorch) - Tensors and Dynamic neural networks in Python with strong GPU acceleration.
  - [tensorflow](https://github.com/tensorflow/tensorflow) - The most popular Deep Learning framework created by Google.
  - [keras](https://github.com/keras-team/keras) - A high-level deep learning library with support for JAX, TensorFlow, and PyTorch backends.
  - [jax](https://github.com/jax-ml/jax) - A library for high-performance numerical computing with automatic differentiation and JIT compilation.
  - [pytorch-lightning](https://github.com/Lightning-AI/pytorch-lightning) - Deep learning framework to train, deploy, and ship AI products Lightning fast.
- Reinforcement Learning
  - [gymnasium](https://github.com/Farama-Foundation/Gymnasium) - A standard API for reinforcement learning environments with popular reference environments ([gym](https://github.com/openai/gym) successor).
  - [stable-baselines3](https://github.com/DLR-RM/stable-baselines3) - PyTorch implementations of Stable Baselines (deep) reinforcement learning algorithms.

### Machine Learning

_Libraries for Machine Learning. Also see [awesome-machine-learning](https://github.com/josephmisiti/awesome-machine-learning#python)._

- General
  - [scikit-learn](https://github.com/scikit-learn/scikit-learn) - The most popular Python library for Machine Learning with extensive documentation and community support.
  - [pgmpy](https://github.com/pgmpy/pgmpy) - A Python library for probabilistic graphical models and Bayesian networks.
  - [feature-engine](https://github.com/feature-engine/feature_engine) - sklearn compatible API with the widest toolset for feature engineering and selection.
- Gradient Boosting
  - [xgboost](https://github.com/dmlc/xgboost) - A scalable, portable, and distributed gradient boosting library.
  - [lightgbm](https://github.com/lightgbm-org/LightGBM) - A fast, distributed, high performance gradient boosting framework.
  - [catboost](https://github.com/catboost/catboost) - A fast, scalable, high performance gradient boosting on decision trees library.
- Time Series Forecasting
  - [timesfm](https://github.com/google-research/timesfm) - A pretrained foundation model from Google Research for time-series forecasting.

### Natural Language Processing

_Libraries for working with human languages._

- General
  - [nltk](https://github.com/nltk/nltk) - A leading platform for building Python programs to work with human language data.
  - [spacy](https://github.com/explosion/spaCy) - A library for industrial-strength natural language processing in Python and Cython.
  - [gensim](https://github.com/piskvorky/gensim) - Topic Modeling for Humans.
  - [stanza](https://github.com/stanfordnlp/stanza) - The Stanford NLP Group's official Python library, supporting 60+ languages.
- Chinese
  - [jieba](https://github.com/fxsjy/jieba) - The most popular Chinese text segmentation library.
  - [pypinyin](https://github.com/mozillazg/python-pinyin) - Convert Chinese hanzi (漢字) to pinyin (拼音).
  - [pangu.py](https://github.com/vinta/pangu.py) - Paranoid text spacing.

### Computer Vision

_Libraries for Computer Vision._

- General
  - [opencv-python](https://github.com/opencv/opencv-python) - Open Source Computer Vision Library.
  - [ultralytics](https://github.com/ultralytics/ultralytics) - Ultralytics YOLO for object detection, segmentation, pose estimation, and classification with state-of-the-art accuracy and speed.
  - [kornia](https://github.com/kornia/kornia/) - Open Source Differentiable Computer Vision Library for PyTorch.
  - [fiftyone](https://github.com/voxel51/fiftyone) - The open-source tool for building high-quality datasets and computer vision models.
- OCR
  - [pytesseract](https://github.com/madmaze/pytesseract) - A wrapper for [Google Tesseract OCR](https://github.com/tesseract-ocr).
  - [easyocr](https://github.com/JaidedAI/EasyOCR) - Ready-to-use OCR with 40+ languages supported.

### Recommender Systems

_Libraries for building recommender systems._

- [annoy](https://github.com/spotify/annoy) - Approximate Nearest Neighbors in C++/Python optimized for memory usage.
- [implicit](https://github.com/benfred/implicit) - A fast Python implementation of collaborative filtering for implicit datasets.
- [scikit-surprise](https://github.com/NicolasHug/Surprise) - A scikit for building and analyzing recommender systems.

**Web Development**

### Web Frameworks

_Traditional full stack web frameworks. Also see [Web APIs](#web-apis)._

- Synchronous
  - [flask](https://github.com/pallets/flask) - A microframework for Python.
    - [awesome-flask](https://github.com/humiaozuzu/awesome-flask)
  - [django](https://github.com/django/django) - The most popular web framework in Python.
    - [awesome-django](https://github.com/wsvincent/awesome-django)
  - [bottle](https://github.com/bottlepy/bottle) - A fast and simple micro-framework distributed as a single file with no dependencies.
  - [pyramid](https://github.com/Pylons/pyramid) - A small, fast, down-to-earth, open source Python web framework.
    - [awesome-pyramid](https://github.com/uralbash/awesome-pyramid)
  - [fasthtml](https://github.com/AnswerDotAI/fasthtml) - The fastest way to create an HTML app.
    - [awesome-fasthtml](https://github.com/amosgyamfi/awesome-fasthtml)
- Asynchronous
  - [starlette](https://github.com/Kludex/starlette) - A lightweight ASGI framework and toolkit for building high-performance async services.
  - [tornado](https://github.com/tornadoweb/tornado) - A web framework and asynchronous networking library.
  - [litestar](https://github.com/litestar-org/litestar) - Production-ready, capable and extensible ASGI Web framework.
  - [reflex](https://github.com/reflex-dev/reflex) - A framework for building reactive, full-stack web applications entirely with Python.

### Web APIs

_Libraries for building RESTful, GraphQL, and RPC APIs._

- Django
  - [django-rest-framework](https://github.com/encode/django-rest-framework) - A powerful and flexible toolkit to build web APIs.
  - [django-ninja](https://github.com/vitalik/django-ninja) - Fast, Django REST framework based on type hints and Pydantic.
  - [strawberry-django](https://github.com/strawberry-graphql/strawberry-django) - Strawberry GraphQL integration with Django.
  - [django-modern-rest](https://github.com/wemake-services/django-modern-rest) - Modern REST with speed, types, async, `msgspec`, `pydantic` and other goodies!
- Flask
  - [apiflask](https://github.com/apiflask/apiflask) - A lightweight Python web API framework based on Flask and Marshmallow.
- Framework Agnostic
  - [fastapi](https://github.com/fastapi/fastapi) - A modern, fast, web framework for building APIs with standard Python type hints.
  - [connexion](https://github.com/spec-first/connexion) - A spec-first framework that automatically handles requests based on your OpenAPI specification.
  - [strawberry](https://github.com/strawberry-graphql/strawberry) - A GraphQL library that leverages Python type annotations for schema definition.
- RPC
  - [grpcio](https://github.com/grpc/grpc) - HTTP/2-based RPC framework with Python bindings, built by Google.

### Web Servers

_ASGI and WSGI compatible web servers._

- ASGI
  - [uvicorn](https://github.com/Kludex/uvicorn) - A lightning-fast ASGI server implementation, using uvloop and httptools.
  - [granian](https://github.com/emmett-framework/granian) - A Rust HTTP server for Python applications built on top of Hyper and Tokio, supporting WSGI/ASGI/RSGI.
  - [hypercorn](https://github.com/pgjones/hypercorn) - An ASGI and WSGI Server based on Hyper libraries and inspired by Gunicorn.
- WSGI
  - [gunicorn](https://github.com/benoitc/gunicorn) - Pre-forked, ported from Ruby's Unicorn project.
  - [waitress](https://github.com/Pylons/waitress) - Multi-threaded, powers Pyramid.

### WebSocket

_Libraries for working with WebSocket._

- [websockets](https://github.com/python-websockets/websockets) - A library for building WebSocket servers and clients with a focus on correctness and simplicity.
- [channels](https://github.com/django/channels) - Developer-friendly asynchrony for Django.
- [flask-socketio](https://github.com/miguelgrinberg/Flask-SocketIO) - Socket.IO integration for Flask applications.
- [autobahn-python](https://github.com/crossbario/autobahn-python) - WebSocket & WAMP for Python on Twisted and [asyncio](https://docs.python.org/3/library/asyncio.html).

### Template Engines

_Libraries and tools for templating and lexing._

- [jinja](https://github.com/pallets/jinja) - A modern and designer friendly templating language.
- [mako](https://github.com/sqlalchemy/mako) - Hyperfast and lightweight templating for the Python platform.

### Web Asset Management

_Tools for managing, storing, compressing and minifying website assets._

- [django-storages](https://github.com/jschneier/django-storages) - A collection of custom storage back ends for Django.
- [django-compressor](https://github.com/django-compressor/django-compressor) - Compresses linked and inline JavaScript or CSS into a single cached file.

### Authentication

_Libraries for implementing authentication schemes._

- OAuth
  - [oauthlib](https://github.com/oauthlib/oauthlib) - A generic and thorough implementation of the OAuth request-signing logic.
  - [authlib](https://github.com/authlib/authlib) - A comprehensive library for building OAuth, OpenID Connect, and JWT/JWS/JWE/JWK/JWA.
  - [django-allauth](https://github.com/pennersr/django-allauth) - Authentication app for Django that "just works."
  - [django-oauth-toolkit](https://github.com/django-oauth/django-oauth-toolkit) - OAuth 2 goodies for Django.
- JWT
  - [pyjwt](https://github.com/jpadilla/pyjwt) - JSON Web Token implementation in Python.
- Permissions
  - [django-guardian](https://github.com/django-guardian/django-guardian) - Implementation of per-object permissions for Django.
  - [django-rules](https://github.com/dfunckt/django-rules) - A tiny but powerful app providing object-level permissions to Django, without requiring a database.

### Admin Panels

_Libraries for administrative interfaces._

- [flask-admin](https://github.com/pallets-eco/flask-admin) - Simple and extensible administrative interface framework for Flask.
- [django-unfold](https://github.com/unfoldadmin/django-unfold) - Elevate your Django admin with a stunning modern interface, powerful features, and seamless user experience.
- [django-grappelli](https://github.com/sehmaschine/django-grappelli) - A jazzy skin for the Django Admin-Interface.

### CMS

_Content Management Systems._

- [wagtail](https://github.com/wagtail/wagtail) - A Django content management system.
- [django-cms](https://github.com/django-cms/django-cms) - The easy-to-use and developer-friendly enterprise CMS powered by Django.

### ERP

_Enterprise resource planning frameworks._

- [odoo](https://github.com/odoo/odoo) - A suite of open source business apps: CRM, e-commerce, accounting, inventory, and thousands of community modules.

### Static Site Generators

_Static site generator is a software that takes some text + templates as input and produces HTML files on the output._

- [pelican](https://github.com/getpelican/pelican) - Static site generator that supports Markdown and reST syntax.
- [nikola](https://github.com/getnikola/nikola) - A static website and blog generator.

**HTTP & Scraping**

### HTTP Clients

_Libraries for working with HTTP._

- Clients
  - [requests](https://github.com/psf/requests) - HTTP Requests for Humans.
  - [httpx](https://github.com/encode/httpx) - A next generation HTTP client for Python.
  - [aiohttp](https://github.com/aio-libs/aiohttp) - Asynchronous HTTP client/server framework for asyncio and Python.
  - [urllib3](https://github.com/urllib3/urllib3) - A HTTP library with thread-safe connection pooling, file post support, sanity friendly.
- URL Manipulation
  - [yarl](https://github.com/aio-libs/yarl) - Yet another URL library.
  - [httpx.URL](https://www.python-httpx.org/api/) - The immutable URL class bundled with HTTPX.

### Web Scraping

_Libraries to automate web scraping and extract web content._

- Frameworks
  - [browser-use](https://github.com/browser-use/browser-use) - Make websites accessible for AI agents with easy browser automation.
  - [scrapy](https://github.com/scrapy/scrapy) - A fast high-lev
...[truncated]

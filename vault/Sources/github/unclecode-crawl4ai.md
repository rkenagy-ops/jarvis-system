---
type: source
repo: unclecode/crawl4ai
url: https://github.com/unclecode/crawl4ai
---

# unclecode/crawl4ai

🚀🤖 Crawl4AI: Open-source LLM Friendly Web Crawler & Scraper. Don't be shy, join here: https://discord.gg/jP8KfhDhyN

GitHub: https://github.com/unclecode/crawl4ai

## README

# 🚀🤖 Crawl4AI: Open-source LLM Friendly Web Crawler & Scraper.

<div align="center">

<a href="https://trendshift.io/repositories/11716" target="_blank"><img src="https://trendshift.io/api/badge/repositories/11716" alt="unclecode%2Fcrawl4ai | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[![GitHub Stars](https://img.shields.io/github/stars/unclecode/crawl4ai?style=social)](https://github.com/unclecode/crawl4ai/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/unclecode/crawl4ai?style=social)](https://github.com/unclecode/crawl4ai/network/members)

[![PyPI version](https://badge.fury.io/py/crawl4ai.svg)](https://badge.fury.io/py/crawl4ai)
[![Python Version](https://img.shields.io/pypi/pyversions/crawl4ai)](https://pypi.org/project/crawl4ai/)
[![Downloads](https://static.pepy.tech/badge/crawl4ai/month)](https://pepy.tech/project/crawl4ai)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/unclecode?style=flat&logo=GitHub-Sponsors&label=Sponsors&color=pink)](https://github.com/sponsors/unclecode)

---
#### 🚀 Crawl4AI Cloud API — Closed Beta (Launching Soon)
Reliable, large-scale web extraction, now built to be _**drastically more cost-effective**_ than any of the existing solutions.

👉 **Apply [here](https://forms.gle/E9MyPaNXACnAMaqG7) for early access**  
_We’ll be onboarding in phases and working closely with early users.
Limited slots._

---

<p align="center">
    <a href="https://x.com/crawl4ai">
      <img src="https://img.shields.io/badge/Follow%20on%20X-000000?style=for-the-badge&logo=x&logoColor=white" alt="Follow on X" />
    </a>
    <a href="https://www.linkedin.com/company/crawl4ai">
      <img src="https://img.shields.io/badge/Follow%20on%20LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" alt="Follow on LinkedIn" />
    </a>
    <a href="https://discord.gg/jP8KfhDhyN">
      <img src="https://img.shields.io/badge/Join%20our%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join our Discord" />
    </a>
  </p>
</div>

Crawl4AI turns the web into clean, LLM ready Markdown for RAG, agents, and data pipelines. Fast, controllable, battle tested by a 50k+ star community.

[✨ Check out latest update v0.9.2](#-recent-updates)

✨ **New in v0.9.2**: Maintenance patch release. Fixes a `MemoryAdaptiveDispatcher` task/page leak when a streaming crawl is closed, Docker Playground "Advanced Config" and Monitor WebSocket auth, Playwright headless-shell packaging, and GPU (`ENABLE_GPU=true`) Docker builds. [Release notes →](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.9.2.md)

✨ Recent v0.9.0: Major secure-by-default release of the Docker API server. Auth is on by default, the server binds loopback unless given a token, and the request body is now an untrusted trust boundary. [Release notes →](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.9.0.md)

✨ Recent v0.8.7: Security-hardening release. Fixes critical Docker API vulnerabilities (RCE, SSRF, auth bypass, file write, XSS, hardcoded JWT secret), adds DomainMapper, and ships scraping, deep-crawl, and LLM fixes. [Release notes →](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.8.7.md)

✨ Previous v0.8.0: Crash Recovery & Prefetch Mode! Deep crawl crash recovery with `resume_state` and `on_state_change` callbacks for long-running crawls. New `prefetch=True` mode for 5-10x faster URL discovery. [Release notes →](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.8.0.md)

✨ Previous v0.7.8: Stability & Bug Fix Release! 11 bug fixes addressing Docker API issues, LLM extraction improvements, URL handling fixes, and dependency updates. [Release notes →](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.7.8.md)

<details>
  <summary>🤓 <strong>My Personal Story</strong></summary>

I grew up on an Amstrad, thanks to my dad, and never stopped building. In grad school I specialized in NLP and built crawlers for research. That’s where I learned how much extraction matters.

In 2023, I needed web-to-Markdown. The “open source” option wanted an account, API token, and $16, and still under-delivered. I went turbo anger mode, built Crawl4AI in days, and it went viral. Now it’s the most-starred crawler on GitHub.

I made it open source for **availability**, anyone can use it without a gate. Now I’m building the platform for **affordability**, anyone can run serious crawls without breaking the bank. If that resonates, join in, send feedback, or just crawl something amazing.
</details>


<details>
  <summary>Why developers pick Crawl4AI</summary>

- **LLM ready output**, smart Markdown with headings, tables, code, citation hints
- **Fast in practice**, async browser pool, caching, minimal hops
- **Full control**, sessions, proxies, cookies, user scripts, hooks
- **Adaptive intelligence**, learns site patterns, explores only what matters
- **Deploy anywhere**, zero keys, CLI and Docker, cloud friendly
</details>


## 🚀 Quick Start 

1. Install Crawl4AI:
```bash
# Install the package
pip install -U crawl4ai

# For pre release versions
pip install crawl4ai --pre

# Run post-installation setup
crawl4ai-setup

# Verify your installation
crawl4ai-doctor
```

If you encounter any browser-related issues, you can install them manually:
```bash
python -m playwright install --with-deps chromium
```

2. Run a simple web crawl with Python:
```python
import asyncio
from crawl4ai import *

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.nbcnews.com/business",
        )
        print(result.markdown)

if __name__ == "__main__":
    asyncio.run(main())
```

3. Or use the new command-line interface:
```bash
# Basic crawl with markdown output
crwl https://www.nbcnews.com/business -o markdown

# Deep crawl with BFS strategy, max 10 pages
crwl https://docs.crawl4ai.com --deep-crawl bfs --max-pages 10

# Use LLM extraction with a specific question
crwl https://www.example.com/products -q "Extract all product prices"
```

## 💖 Support Crawl4AI

> 🎉 **Sponsorship Program Now Open!** After powering 51K+ developers and 1 year of growth, Crawl4AI is launching dedicated support for **startups** and **enterprises**. Be among the first 50 **Founding Sponsors** for permanent recognition in our Hall of Fame.

Crawl4AI is the #1 trending open-source web crawler on GitHub. Your support keeps it independent, innovative, and free for the community — while giving you direct access to premium benefits.

<div align="">
  
[![Become a Sponsor](https://img.shields.io/badge/Become%20a%20Sponsor-pink?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/unclecode)  
[![Current Sponsors](https://img.shields.io/github/sponsors/unclecode?style=for-the-badge&logo=github&label=Current%20Sponsors&color=green)](https://github.com/sponsors/unclecode)

</div>

### 🤝 Sponsorship Tiers

- **🌱 Believer ($5/mo)** — Join the movement for data democratization  
- **🚀 Builder ($50/mo)** — Priority support & early access to features  
- **💼 Growing Team ($500/mo)** — Bi-weekly syncs & optimization help  
- **🏢 Data Infrastructure Partner ($2000/mo)** — Full partnership with dedicated support  
  *Custom arrangements available - see [SPONSORS.md](SPONSORS.md) for details & contact*

**Why sponsor?**  
No rate-limited APIs. No lock-in. Build and own your data pipeline with direct guidance from the creator of Crawl4AI.

[See All Tiers & Benefits →](https://github.com/sponsors/unclecode)


## ✨ Features 

<details>
<summary>📝 <strong>Markdown Generation</strong></summary>

- 🧹 **Clean Markdown**: Generates clean, structured Markdown with accurate formatting.
- 🎯 **Fit Markdown**: Heuristic-based filtering to remove noise and irrelevant parts for AI-friendly processing.
- 🔗 **Citations and References**: Converts page links into a numbered reference list with clean citations.
- 🛠️ **Custom Strategies**: Users can create their own Markdown generation strategies tailored to specific needs.
- 📚 **BM25 Algorithm**: Employs BM25-based filtering for extracting core information and removing irrelevant content. 
</details>

<details>
<summary>📊 <strong>Structured Data Extraction</strong></summary>

- 🤖 **LLM-Driven Extraction**: Supports all LLMs (open-source and proprietary) for structured data extraction.
- 🧱 **Chunking Strategies**: Implements chunking (topic-based, regex, sentence-level) for targeted content processing.
- 🌌 **Cosine Similarity**: Find relevant content chunks based on user queries for semantic extraction.
- 🔎 **CSS-Based Extraction**: Fast schema-based data extraction using XPath and CSS selectors.
- 🔧 **Schema Definition**: Define custom schemas for extracting structured JSON from repetitive patterns.

</details>

<details>
<summary>🌐 <strong>Browser Integration</strong></summary>

- 🖥️ **Managed Browser**: Use user-owned browsers with full control, avoiding bot detection.
- 🔄 **Remote Browser Control**: Connect to Chrome Developer Tools Protocol for remote, large-scale data extraction.
- 👤 **Browser Profiler**: Create and manage persistent profiles with saved authentication states, cookies, and settings.
- 🔒 **Session Management**: Preserve browser states and reuse them for multi-step crawling.
- 🧩 **Proxy Support**: Seamlessly connect to proxies with authentication for secure access.
- ⚙️ **Full Browser Control**: Modify headers, cookies, user agents, and more for tailored crawling setups.
- 🌍 **Multi-Browser Support**: Compatible with Chromium, Firefox, and WebKit.
- 📐 **Dynamic Viewport Adjustment**: Automatically adjusts the browser viewport to match page content, ensuring complete rendering and capturing of all elements.

</details>

<details>
<summary>🔎 <strong>Crawling & Scraping</strong></summary>

- 🖼️ **Media Support**: Extract images, audio, videos, and responsive image formats like `srcset` and `picture`.
- 🚀 **Dynamic Crawling**: Execute JS and wait for async or sync for dynamic content extraction.
- 📸 **Screenshots**: Capture page screenshots during crawling for debugging or analysis.
- 📂 **Raw Data Crawling**: Directly process raw HTML (`raw:`) or local files (`file://`).
- 🔗 **Comprehensive Link Extraction**: Extracts internal, external links, and embedded iframe content.
- 🛠️ **Customizable Hooks**: Define hooks at every step to customize crawling behavior (supports both string and function-based APIs).
- 💾 **Caching**: Cache data for improved speed and to avoid redundant fetches.
- 📄 **Metadata Extraction**: Retrieve structured metadata from web pages.
- 📡 **IFrame Content Extraction**: Seamless extraction from embedded iframe content.
- 🕵️ **Lazy Load Handling**: Waits for images to fully load, ensuring no content is missed due to lazy loading.
- 🔄 **Full-Page Scanning**: Simulates scrolling to load and capture all dynamic content, perfect for infinite scroll pages.

</details>

<details>
<summary>🚀 <strong>Deployment</strong></summary>

- 🐳 **Dockerized Setup**: Optimized Docker image with FastAPI server for easy deployment.
- 🔑 **Secure Authentication**: Built-in JWT token authentication for API security.
- 🔄 **API Gateway**: One-click deployment with secure token authentication for API-based workflows.
- 🌐 **Scalable Architecture**: Designed for mass-scale production and optimized server performance.
- ☁️ **Cloud Deployment**: Ready-to-deploy configurations for major cloud platforms.

</details>

<details>
<summary>🎯 <strong>Additional Features</strong></summary>

- 🕶️ **Stealth Mode**: Avoid bot detection by mimicking real users.
- 🏷️ **Tag-Based Content Extraction**: Refine crawling based on custom tags, headers, or metadata.
- 🔗 **Link Analysis**: Extract and analyze all links for detailed data exploration.
- 🛡️ **Error Handling**: Robust error management for seamless execution.
- 🔐 **CORS & Static Serving**: Supports filesystem-based caching and cross-origin requests.
- 📖 **Clear Documentation**: Simplified and updated guides for onboarding and advanced usage.
- 🙌 **Community Recognition**: Acknowledges contributors and pull requests for transparency.

</details>

## Try it Now!

✨ Play around with this [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1SgRPrByQLzjRfwoRNq1wSGE9nYY_EE8C?usp=sharing)

✨ Visit our [Documentation Website](https://docs.crawl4ai.com/)

## Installation 🛠️

Crawl4AI offers flexible installation options to suit various use cases. You can install it as a Python package or use Docker.

<details>
<summary>🐍 <strong>Using pip</strong></summary>

Choose the installation option that best fits your needs:

### Basic Installation

For basic web crawling and scraping tasks:

```bash
pip install crawl4ai
crawl4ai-setup # Setup the browser
```

By default, this will install the asynchronous version of Crawl4AI, using Playwright for web crawling.

👉 **Note**: When you install Crawl4AI, the `crawl4ai-setup` should automatically install and set up Playwright. However, if you encounter any Playwright-related errors, you can manually install it using one of these methods:

1. Through the command line:

   ```bash
   playwright install
   ```

2. If the above doesn't work, try this more specific command:

   ```bash
   python -m playwright install chromium
   ```

This second method has proven to be more reliable in some cases.

---

### Installation with Synchronous Version

The sync version is deprecated and will be removed in future versions. If you need the synchronous version using Selenium:

```bash
pip install crawl4ai[sync]
```

---

### Development Installation

For contributors who plan to modify the source code:

```bash
git clone https://github.com/unclecode/crawl4ai.git
cd crawl4ai
pip install -e .                    # Basic installation in editable mode
```

Install optional features:

```bash
pip install -e ".[torch]"           # With PyTorch features
pip install -e ".[transformer]"     # With Transformer features
pip install -e ".[cosine]"          # With cosine similarity features
pip install -e ".[sync]"            # With synchronous crawling (Selenium)
pip install -e ".[all]"             # Install all optional features
```

</details>

<details>
<summary>🐳 <strong>Docker Deployment</strong></summary>

> 🚀 **Now Available!** Our completely redesigned Docker implementation is here! This new solution makes deployment more efficient and seamless than ever.

### New Docker Features

The new Docker implementation includes:
- **Real-time Monitoring Dashboard** with live system metrics and browser pool visibility
- **Browser pooling** with page pre-warming for faster response times
- **Interactive playground** to test and generate request code
- **MCP integration** for direct connection to AI tools like Claude Code
- **Comprehensive API endpoints** including HTML extraction, screenshots, PDF generation, and JavaScript execution
- **Multi-architecture support** with automatic detection (AMD64/ARM64)
- **Optimized resources** with improved memory management

### Getting Started

```bash
# Pull and run the latest release
docker pull unclecode/crawl4ai:latest
docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest

# Visit the monitoring dashboard at http://localhost:11235/dashboard
# Or the playground at http://localhost:11235/playground
```

### Quick Test

Run a quick test (works for both Docker options):

```python
import requests

# Submit a crawl job
response = requests.post(
    "http://localhost:11235/crawl",
    json={"urls": ["https://example.com"], "priority": 10}
)
if response.status_code == 200:
    print("Crawl job submitted successfully.")
    
if "results" in response.json():
    results = response.json()["results"]
    print("Crawl job completed. Results:")
    for result in results:
        print(result)
else:
    task_id = response.json()["task_id"]
    print(f"Crawl job submitted. Task ID:: {task_id}")
    result = requests.get(f"http://localhost:11235/task/{task_id}")
```

For more examples, see our [Docker Examples](https://github.com/unclecode/crawl4ai/blob/main/docs/examples/docker_example.py). For advanced configuration, monitoring features, and production deployment, see our [Self-Hosting Guide](https://docs.crawl4ai.com/core/self-hosting/).

</details>

---

## 🔬 Advanced Usage Examples 🔬

You can check the project structure in the directory [docs/examples](https://github.com/unclecode/crawl4ai/tree/main/docs/examples). Over there, you can find a variety of examples; here, some popular examples are shared.

<details>
<summary>📝 <strong>Heuristic Markdown Generation with Clean and Fit Markdown</strong></summary>

```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter, BM25ContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

async def main():
    browser_config = BrowserConfig(
        headless=True,  
        verbose=True,
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed", min_word_threshold=0)
        ),
        # markdown_generator=DefaultMarkdownGenerator(
        #     content_filter=BM25ContentFilter(user_query="WHEN_WE_FOCUS_BASED_ON_A_USER_QUERY", bm25_threshold=1.0)
        # ),
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://docs.micronaut.io/4.9.9/guide/",
            config=run_config
        )
        print(len(result.markdown.raw_markdown))
        print(len(result.markdown.fit_markdown))

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

<details>
<summary>🖥️ <strong>Executing JavaScript & Extract Structured Data without LLMs</strong></summary>

```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai import JsonCssExtractionStrategy
import json

async def main():
    schema = {
    "name": "KidoCode Courses",
    "baseSelector": "section.charge-methodology .w-tab-content > div",
    "fields": [
        {
            "name": "section_title",
            "selector": "h3.heading-50",
            "type": "text",
        },
        {
            "name": "section_description",
            "selector": ".charge-content",
            "type": "text",
        },
        {
            "name": "course_name",
            "selector": ".text-block-93",
            "type": "text",
        },
        {
            "name": "course_description",
            "selector": ".course-content-text",
            "type": "text",
        },
        {
            "name": "course_icon",
            "selector": ".image-92",
            "type": "attribute",
            "attribute": "src"
        }
    ]
}

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=False,
        verbose=True
    )
    run_config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
        js_code=["""(async () => {const tabs = document.querySelectorAll("section.charge-methodology .tabs-menu-3 > div");for(let tab of tabs) {tab.scrollIntoView();tab.click();await new Promise(r => setTimeout(r, 500));}})();"""],
        cache_mode=CacheMode.BYPASS
    )
        
    async with AsyncWebCrawler(config=browser_config) as crawler:
        
        result = await crawler.arun(
            url="https://www.kidocode.com/degrees/technology",
            config=run_config
        )

        companies = json.loads(result.extracted_content)
        print(f"Successfully extracted {len(companies)} companies")
        print(json.dumps(companies[0], inden
...[truncated]

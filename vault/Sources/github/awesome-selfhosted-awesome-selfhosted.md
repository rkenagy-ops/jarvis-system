---
type: source
repo: awesome-selfhosted/awesome-selfhosted
url: https://github.com/awesome-selfhosted/awesome-selfhosted
---

# awesome-selfhosted/awesome-selfhosted

A list of Free Software network services and web applications which can be hosted on your own servers

GitHub: https://github.com/awesome-selfhosted/awesome-selfhosted

## README

# Awesome-Selfhosted

[![Awesome](_static/awesome.png)](https://github.com/sindresorhus/awesome) [![](https://github.com/awesome-selfhosted/awesome-selfhosted-data/actions/workflows/check-dead-links.yml/badge.svg)](https://github.com/awesome-selfhosted/awesome-selfhosted-data/issues/1) [![](https://github.com/awesome-selfhosted/awesome-selfhosted-data/actions/workflows/check-unmaintained-projects.yml/badge.svg)](https://github.com/awesome-selfhosted/awesome-selfhosted-data/issues/1) [![](https://img.shields.io/liberapay/goal/awesome-selfhosted.svg?logo=liberapay)](https://liberapay.com/awesome-selfhosted/)

Self-hosting is the practice of hosting and managing applications on your own server(s) instead of consuming from [SaaSS](https://www.gnu.org/philosophy/who-does-that-server-really-serve.html) providers.

This is a list of [Free](https://en.wikipedia.org/wiki/Free_software) Software [network services](https://en.wikipedia.org/wiki/Network_service) and [web applications](https://en.wikipedia.org/wiki/Web_application) which can be hosted on your own server(s). Non-Free software is listed on the [Non-Free](https://github.com/awesome-selfhosted/awesome-selfhosted/blob/master/non-free.md) page.

**[HTML version](https://awesome-selfhosted.net/) (recommended)**, [Markdown version](https://github.com/awesome-selfhosted/awesome-selfhosted) (legacy).

See [Contributing](#contributing).

--------------------

## Table of contents

- [Software](#software)
  - [Analytics](#analytics)
  - [Archiving and Digital Preservation (DP)](#archiving-and-digital-preservation-dp)
  - [Automation](#automation)
  - [Backup](#backup)
  - [Blogging Platforms](#blogging-platforms)
  - [Booking and Scheduling](#booking-and-scheduling)
  - [Bookmarks and Link Sharing](#bookmarks-and-link-sharing)
  - [Calendar & Contacts](#calendar--contacts)
  - [Communication - Custom Communication Systems](#communication---custom-communication-systems)
  - [Communication - Email - Complete Solutions](#communication---email---complete-solutions)
  - [Communication - Email - Mail Delivery Agents](#communication---email---mail-delivery-agents)
  - [Communication - Email - Mail Transfer Agents](#communication---email---mail-transfer-agents)
  - [Communication - Email - Mailing Lists and Newsletters](#communication---email---mailing-lists-and-newsletters)
  - [Communication - Email - Webmail Clients](#communication---email---webmail-clients)
  - [Communication - IRC](#communication---irc)
  - [Communication - SIP](#communication---sip)
  - [Communication - Social Networks and Forums](#communication---social-networks-and-forums)
  - [Communication - Video Conferencing](#communication---video-conferencing)
  - [Communication - XMPP - Servers](#communication---xmpp---servers)
  - [Communication - XMPP - Web Clients](#communication---xmpp---web-clients)
  - [Community-Supported Agriculture (CSA)](#community-supported-agriculture-csa)
  - [Conference Management](#conference-management)
  - [Content Management Systems (CMS)](#content-management-systems-cms)
  - [Customer Relationship Management (CRM)](#customer-relationship-management-crm)
  - [Database Management](#database-management)
  - [DNS](#dns)
  - [Document Management](#document-management)
  - [Document Management - E-books](#document-management---e-books)
  - [Document Management - Institutional Repository and Digital Library Software](#document-management---institutional-repository-and-digital-library-software)
  - [Document Management - Integrated Library Systems (ILS)](#document-management---integrated-library-systems-ils)
  - [E-commerce](#e-commerce)
  - [Federated Identity & Authentication](#federated-identity--authentication)
  - [Feed Readers](#feed-readers)
  - [File Transfer & Synchronization](#file-transfer--synchronization)
  - [File Transfer - Distributed Filesystems](#file-transfer---distributed-filesystems)
  - [File Transfer - Object Storage & File Servers](#file-transfer---object-storage--file-servers)
  - [File Transfer - Peer-to-peer Filesharing](#file-transfer---peer-to-peer-filesharing)
  - [File Transfer - Single-click & Drag-n-drop Upload](#file-transfer---single-click--drag-n-drop-upload)
  - [File Transfer - Web-based File Managers](#file-transfer---web-based-file-managers)
  - [Games](#games)
  - [Games - Administrative Utilities & Control Panels](#games---administrative-utilities--control-panels)
  - [Genealogy](#genealogy)
  - [Generative Artificial Intelligence (GenAI)](#generative-artificial-intelligence-genai)
  - [Groupware](#groupware)
  - [Health and Fitness](#health-and-fitness)
  - [Human Resources Management (HRM)](#human-resources-management-hrm)
  - [Identity Management](#identity-management)
  - [Internet of Things (IoT)](#internet-of-things-iot)
  - [Inventory Management](#inventory-management)
  - [Knowledge Management Tools](#knowledge-management-tools)
  - [Learning and Courses](#learning-and-courses)
  - [Manufacturing](#manufacturing)
  - [Maps and Global Positioning System (GPS)](#maps-and-global-positioning-system-gps)
  - [Media Management](#media-management)
  - [Media Streaming](#media-streaming)
  - [Media Streaming - Audio Streaming](#media-streaming---audio-streaming)
  - [Media Streaming - Multimedia Streaming](#media-streaming---multimedia-streaming)
  - [Media Streaming - Video Streaming](#media-streaming---video-streaming)
  - [Miscellaneous](#miscellaneous)
  - [Money, Budgeting & Management](#money-budgeting--management)
  - [Monitoring & Status Pages](#monitoring--status-pages)
  - [Network Utilities](#network-utilities)
  - [Note-taking & Editors](#note-taking--editors)
  - [Office Suites](#office-suites)
  - [Password Managers](#password-managers)
  - [Pastebins](#pastebins)
  - [Personal Dashboards](#personal-dashboards)
  - [Photo Galleries](#photo-galleries)
  - [Polls and Events](#polls-and-events)
  - [Proxy](#proxy)
  - [Recipe Management](#recipe-management)
  - [Remote Access](#remote-access)
  - [Resource Planning](#resource-planning)
  - [Search Engines](#search-engines)
  - [Self-hosting Solutions](#self-hosting-solutions)
  - [Software Development](#software-development)
  - [Software Development - API Management](#software-development---api-management)
  - [Software Development - Continuous Integration & Deployment](#software-development---continuous-integration--deployment)
  - [Software Development - FaaS & Serverless](#software-development---faas--serverless)
  - [Software Development - Feature Toggle](#software-development---feature-toggle)
  - [Software Development - IDE & Tools](#software-development---ide--tools)
  - [Software Development - Localization](#software-development---localization)
  - [Software Development - Low Code](#software-development---low-code)
  - [Software Development - Project Management](#software-development---project-management)
  - [Software Development - Testing](#software-development---testing)
  - [Static Site Generators](#static-site-generators)
  - [Task Management & To-do Lists](#task-management--to-do-lists)
  - [Ticketing](#ticketing)
  - [Time Tracking](#time-tracking)
  - [Travel Organization](#travel-organization)
  - [URL Shorteners](#url-shorteners)
  - [Video Surveillance](#video-surveillance)
  - [VPN](#vpn)
  - [Web Servers](#web-servers)
  - [Wikis](#wikis)
- [List of Licenses](#list-of-licenses)
- [Anti-features](#anti-features)
- [External Links](#external-links)
- [Contributing](#contributing)
- [License](#license)

--------------------

## Software

### Analytics

**[`^        back to top        ^`](#awesome-selfhosted)**

[Analytics](https://en.wikipedia.org/wiki/Analytics) is the systematic computational analysis of data or statistics. It is used for the discovery, interpretation, and communication of meaningful patterns in data.

_Related: [Database Management](#database-management), [Personal Dashboards](#personal-dashboards)_

- [ANALOG](https://github.com/orangecoloured/analog) - A minimal analytics tool. Tracks events in a span of 10-30 days. `MIT` `Nodejs/Docker`
- [Aptabase](https://aptabase.com/) - Privacy first and simple analytics for mobile and desktop apps. ([Source Code](https://github.com/aptabase/aptabase)) `AGPL-3.0` `Docker`
- [AWStats](http://www.awstats.org/) - Generate statistics from web, streaming, ftp or mail server logfiles. ([Demo](https://www.awstats.org/#DEMO), [Source Code](https://github.com/eldy/awstats)) `GPL-3.0` `Perl`
- [Countly Community Edition](https://count.ly) - Real time mobile and web analytics, crash reporting and push notifications platform. ([Source Code](https://github.com/Countly/countly-server)) `AGPL-3.0` `Nodejs/Docker`
- [d8a.tech](https://d8a.tech) - A data collection service that works with your existing Google Analytics setup to capture user activity and send it straight to your own private database. ([Demo](https://lookerstudio.google.com/u/0/reporting/0e4102b6-c38b-4f55-aa25-c1fe91d1c1e9), [Source Code](https://github.com/d8a-tech/d8a)) `MIT` `Go/Docker`
- [Daily Stars Explorer](https://emanuelef.github.io/daily-stars-explorer) `⚠` - Track GitHub repo trends with daily star insights to see growth and community interest over time. ([Demo](https://emanuelef.github.io/daily-stars-explorer), [Source Code](https://github.com/emanuelef/daily-stars-explorer)) `MIT` `Go/Nodejs/Docker`
- [Druid](https://druid.apache.org) - Distributed, column-oriented, real-time analytics data store. ([Source Code](https://github.com/apache/druid)) `Apache-2.0` `Java/Docker`
- [EDA](https://github.com/jortilles/EDA) - Web application for data analysis and visualization. `AGPL-3.0` `Nodejs/Docker`
- [GoAccess](http://goaccess.io/) - Real-time web log analyzer and interactive viewer that runs in a terminal. ([Source Code](https://github.com/allinurl/goaccess)) `GPL-2.0` `C`
- [GoatCounter](https://www.goatcounter.com) - Easy web statistics without tracking of personal data. ([Source Code](https://github.com/arp242/goatcounter)) `EUPL-1.2` `Go`
- [HitKeep](https://hitkeep.com/) - Privacy-first web analytics with goals, funnels, ecommerce tracking, and team management in a single binary with embedded DuckDB (alternative to Google Analytics, Plausible, Umami). ([Source Code](https://github.com/pascalebeier/hitkeep)) `MIT` `Go/Docker`
- [Litlyx](https://litlyx.com) - All-in-one Analytics Solution. Setup in 30 seconds. Display all your data on an AI-powered dashboard. Fully self-hostable and GDPR compliant. ([Source Code](https://github.com/Litlyx/litlyx)) `Apache-2.0` `Docker`
- [Liwan](https://liwan.dev/) - Privacy-first web analytics. ([Demo](https://demo.liwan.dev/p/liwan.dev), [Source Code](https://github.com/explodingcamera/liwan)) `Apache-2.0` `Rust/Docker`
- [Matomo](https://matomo.org/) - Web analytics that protects your data and your customers' privacy (alternative to Google Analytics). ([Source Code](https://github.com/matomo-org/matomo)) `GPL-3.0` `PHP`
- [Medama Analytics](https://oss.medama.io) - Privacy-first website analytics. Tiny, simple, and cookie-free. ([Demo](https://demo.medama.io), [Source Code](https://github.com/medama-io/medama)) `Apache-2.0/MIT` `Docker/Go`
- [Metabase](https://metabase.com/) - Easy way for everyone in your company to ask questions and learn from data. ([Source Code](https://github.com/metabase/metabase)) `AGPL-3.0` `Java/Docker`
- [Middleware](https://middlewarehq.com/) - Tool designed to help engineering leaders measure and analyze the effectiveness of their teams using the DORA metrics. ([Source Code](https://github.com/middlewarehq/middleware)) `Apache-2.0` `Docker/Python/Nodejs`
- [Netron](https://netron.app/) - Visualizer for neural network and machine learning models. ([Source Code](https://github.com/lutzroeder/netron)) `MIT` `Python/Nodejs`
- [Offen](https://www.offen.dev/) - Fair, lightweight and open web analytics tool. Gain insights while your users have full access to their data. ([Demo](https://www.offen.dev/try-demo/), [Source Code](https://github.com/offen/offen)) `Apache-2.0` `Go/Docker`
- [Plausible Analytics](https://plausible.io/) - Simple, lightweight (< 1 KB) and privacy-friendly web analytics. ([Source Code](https://github.com/plausible/analytics/)) `AGPL-3.0` `Elixir`
- [PostHog](https://posthog.com) - Product analytics, session recording, feature flagging and a/b testing that you can self-host (alternative to Mixpanel, Amplitude, Heap, HotJar, Optimizely). ([Source Code](https://github.com/posthog/posthog)) `MIT` `Python`
- [Postiz](https://postiz.com) `⚠` - Schedule posts, track the performance of your content, and manage all your social media accounts in one place (Alternative to Buffer, Hootsuite, Sprout Social). ([Source Code](https://github.com/gitroomhq/postiz-app)) `AGPL-3.0` `Docker`
- [Prisme Analytics](https://www.prismeanalytics.com) - Privacy-focused and progressive analytics service based on Grafana. ([Source Code](https://github.com/prismelabs/analytics)) `AGPL-3.0/MIT` `Docker`
- [Redash](http://redash.io) - Connect and query your data sources, build dashboards to visualize data and share them with your company. ([Source Code](https://github.com/getredash/redash)) `BSD-2-Clause` `Docker`
- [Rybbit](https://rybbit.com/) - Web and products analytics that is easy to setup and more intuitive (alternative to Google Analytics). ([Demo](https://demo.rybbit.com/1), [Source Code](https://github.com/rybbit-io/rybbit)) `AGPL-3.0` `Docker`
- [Shaper](https://taleshape.com/shaper/docs) - Build Data Dashboards all in SQL. Powered by DuckDB. ([Demo](https://demo.taleshape.com/view/pvggvdpiwb9wlyppuqbyx0nt), [Source Code](https://github.com/taleshape-com/shaper)) `MPL-2.0` `Docker/Nodejs/Python/Go`
- [Socioboard](https://github.com/socioboard/Socioboard-5.0) `⚠` - Social media management, analytics, and reporting platform supporting nine social media networks out-of-the-box. `GPL-3.0` `Nodejs`
- [Statistics for Strava](https://github.com/robiningelbrecht/statistics-for-strava) `⚠` - Statistics dashboard generated from Strava data. ([Demo](https://statistics-for-strava.robiningelbrecht.be/)) `AGPL-3.0` `Docker`
- [Superset](http://superset.apache.org/) - Modern data exploration and visualization platform. ([Source Code](https://github.com/apache/superset)) `Apache-2.0` `Python`
- [Swetrix](https://swetrix.com/) - Ultimate, open-source web analytics to satisfy all your needs. ([Demo](https://swetrix.com/projects/STEzHcB1rALV), [Source Code](https://github.com/Swetrix/selfhosting)) `AGPL-3.0` `Docker`
- [Umami](https://umami.is/) - Simple, fast, privacy-focused alternative to Google Analytics. ([Demo](https://cloud.umami.is/share/LGazGOecbDtaIwDr), [Source Code](https://github.com/umami-software/umami)) `MIT` `Nodejs/Docker`
- [Vince](https://www.vinceanalytics.com/) - Web analytics and dashboard (alternative to Google Analytics). ([Source Code](https://github.com/vinceanalytics/vince)) `AGPL-3.0` `Go/Docker/K8S/deb`


### Archiving and Digital Preservation (DP)

**[`^        back to top        ^`](#awesome-selfhosted)**

Digital [archiving](https://en.wikipedia.org/wiki/Archival_science) and [preservation](https://en.wikipedia.org/wiki/Digital_preservation) software.

_Related: [Backup](#backup), [Content Management Systems (CMS)](#content-management-systems-cms)_

_See also: [awesome-web-archiving](https://github.com/iipc/awesome-web-archiving)_

- [ArchiveBox](https://archivebox.io/) - Create HTML & screenshot archives of sites from your bookmarks, browsing history, RSS feeds, or other sources (alternative to Wayback Machine). ([Demo](https://demo.archivebox.io/), [Source Code](https://github.com/ArchiveBox/ArchiveBox)) `MIT` `Python/Docker`
- [ArchivesSpace](https://archivesspace.org/) - Archives information management application for managing and providing Web access to archives, manuscripts and digital objects. ([Demo](https://archivesspace.org/application/sandbox), [Source Code](https://github.com/archivesspace/archivesspace)) `ECL-2.0` `Ruby`
- [Bichon](https://github.com/rustmailer/bichon) - Email archiving server that syncs from IMAP accounts, indexes emails for full-text search, and provides a REST API. No external database required, includes WebUI with multi-account support. `AGPL-3.0` `Rust/Docker`
- [bitmagnet](https://bitmagnet.io) - BitTorrent indexer, DHT crawler, content classifier and torrent search engine with web UI, GraphQL API and Servarr stack integration. ([Source Code](https://github.com/bitmagnet-io/bitmagnet)) `MIT` `Go/Docker`
- [CKAN](https://ckan.org) - Make open data websites. ([Source Code](https://github.com/ckan/ckan)) `AGPL-3.0` `Python`
- [Collective Access - Providence](https://collectiveaccess.org/) - Highly configurable Web-based framework for management, description, and discovery of digital and physical collections supporting a variety of metadata standards, data types, and media formats. ([Source Code](https://github.com/collectiveaccess/providence)) `GPL-3.0` `PHP`
- [Eonvelope](https://dacid99.gitlab.io/eonvelope) - Email archiving software that allows you to preserve your emails for an indefinite long period of time. ([Source Code](https://gitlab.com/dacid99/eonvelope)) `AGPL-3.0` `K8S/Docker`
- [Ganymede](https://github.com/Zibbp/ganymede) `⚠` - Twitch VOD and live stream archiving platform. Includes a rendered chat for each archive. `GPL-3.0` `Docker`
- [mail-archiver](https://github.com/s1t5/mail-archiver) - Web application for archiving, searching, and exporting emails from multiple accounts (IMAP, M365 or Import). Featuring folder sync, attachment support, mailbox migration and a dashboard. `GPL-3.0` `Docker`
- [Omeka S](https://omeka.org/s/) - Next-generation web publishing platform for institutions interested in connecting digital cultural heritage collections with other resources online. ([Source Code](https://github.com/omeka/omeka-s)) `GPL-3.0` `Nodejs`
- [Open Archiver](https://openarchiver.com/) - Email archiving solution with full-text search and eDiscovery search features. ([Demo](https://github.com/LogicLabs-OU/OpenArchiver?tab=readme-ov-file#-live-demo), [Source Code](https://github.com/LogicLabs-OU/OpenArchiver)) `AGPL-3.0` `Docker`
- [Piler](https://www.mailpiler.org/) - Feature-rich email archiving solution. ([Source Code](https://github.com/jsuto/piler/)) `GPL-3.0` `C/Docker/deb`
- [Wallabag](https://www.wallabag.org) - Wallabag, formerly Poche, is a web application allowing you to save articles to read them later with improved readability. ([Source Code](https://github.com/wallabag/wallabag)) `MIT` `PHP`
- [Wayback](https://github.com/wabarc/wayback) - A self-hosted toolkit for archiving webpages to the Internet Archive, archive.today, IPFS, and local file systems. `GPL-3.0` `Go`


### Automation

**[`^        back to top        ^`](#awesome-selfhosted)**

[Automation](https://en.wikipedia.org/wiki/Automation) software designed to reduce human intervention in processes.

_Related: [Internet of Things (IoT)](#internet-of-things-iot), [Software Development - Continuous Integration & Deployment](#software-development---continuous-integration--deployment), [Media Management](#media-management)_

- [Activepieces](https://www.activepieces.com) - No-code business automation tool like Zapier or Tray. For example, you can send a Slack notification for each new Trello card. ([Source Code](https://github.com/activepieces/activepieces)) `MIT` `Docker`
- [Apache Airflow](https://airflow.apache.org/) - Platform to programmatically author, schedule, and monitor workflows. ([Source Code](https://github.com/apache/airflow/)) `Apache-2.0` `Python/Docker`
- [Automatisch](https://automatisch.io) - Business automation tool that lets you connect different services like Twitter, Slack, and more to automate your business processes (alternative to Zapier). ([Source Code](https://github.com/automatisch/automatisch)) `AGPL-3.0` `Docker`
- [BookBounty](https://github.com/TheWicklowWolf/BookBounty) `⚠` - Retrieve missing Readarr books from Library Gene
...[truncated]

# SDK 参考

# 实例化客户端
要在 Python 中与 Tavily 交互，您必须使用 API 密钥实例化一个客户端。为了提供更大的灵活性，我们同时提供了同步客户端类和异步客户端类。
一旦您创建了客户端，请调用我们支持的方法之一（详见下文）来访问 API。
​
## 同步客户端
from tavily import TavilyClient

client = TavilyClient("tvly-YOUR_API_KEY")
​
## 异步客户端
from tavily import AsyncTavilyClient

client = AsyncTavilyClient("tvly-YOUR_API_KEY")
​

# 塔维利搜索
您可以通过客户端search函数在 Python 中访问 Tavily 搜索。
​
参数
范围	类型	描述	默认	
query （必需的）	str	要运行搜索的查询语句。	—	
auto_parameters	bool	启用此功能后auto_parameters，Tavily 会根据您的查询内容和意图自动配置搜索参数。您仍然可以手动设置其他参数，并且您显式设置的值将覆盖自动设置的值。参数 `<search_name>`、`<search_name>` 和 `<search_name>`include_answer必须include_raw_content始终max_results手动设置，因为它们直接影响响应大小。注意：search_depth当可能改善搜索结果时，`<search_name>` 可能会自动设置为 `<search_name>`。这将消耗 2 个 API 积分。为避免额外费用，您可以显式地将 `<search_name>` 设置search_depth为`<search_name> basic`。	"false"	
search_depth	str	搜索深度。它可以是"basic"或"advanced"。"advanced"“搜索”旨在检索content与您的查询最相关的来源和摘要，而"basic"“搜索”则提供来自每个来源的通用内容摘要。	"basic"	
topic	str	搜索类别。决定将使用哪个代理。支持的值为"general"、"news"和"finance"。	"general"	
time_range	str	时间范围从当前日期往前推算，基于发布日期或最后更新日期。可接受的值包括"day"、"week"、"month"或"year"简写值"d"、、。"w""m""y"	—	
start_date	str	将返回指定起始日期之后的所有结果（基于发布日期或最后更新日期）。必须以 YYYY-MM-DD 格式填写。	—	
end_date	str	将返回指定截止日期之前的所有结果（截止日期以发布日期或最后更新日期为准）。必须以 YYYY-MM-DD 格式填写。	—	
max_results	int	要返回的最大搜索结果数量。该值必须介于 00和 1之间20。	5	
chunks_per_source	int	内容片段是从源中提取的短内容（每个最多 500 个字符）。用于chunks_per_source定义每个源返回的相关内容片段的最大数量，并控制其content长度。内容片段将显示在content字段中，格式为： 。仅当为时<chunk 1> [...] <chunk 2> [...] <chunk 3>可用。search_depth"advanced"	3	
include_images	bool	images在响应中包含图像。返回查询相关图像的顶级列表，以及images每个结果对象内部包含的数组，该数组包含从特定来源提取的图像。	False	
include_image_descriptions	bool	请在回复中包含与查询相关的图片列表及其描述。	False	
include_answer	bool或者str	请提供由LLM根据搜索结果生成的查询的答案。一个"basic"（或True）答案快速但不够详细；一个"advanced"答案则更为详细。	False	
include_raw_content	bool或者str	包含每个搜索结果的已清理和解析的 HTML 内容。"markdown"或者True以 Markdown 格式返回搜索结果内容。"text"返回结果的纯文本可能会增加延迟。	False	
include_domains	list[str]	要在搜索结果中明确显示的域名列表。最多 300 个域名。	[]	
exclude_domains	list[str]	要从搜索结果中排除的域名列表。最多可添加 150 个域名。	[]	
country	str	提升特定国家/地区的搜索结果。这将优先显示来自所选国家/地区的内容。仅当主题为“.”时可用general。	—	
timeout	float	用于向 Tavily API 发送请求的超时时间。	60	
exact_match	bool	确保仅返回包含查询中确切引用短语的搜索结果，忽略同义词或语义变体。将目标短语用引号括起来（例如：`\sqrt{"x "John Smith"" ...	False	
include_favicon	bool	是否包含每个搜索结果的网站图标网址。	False	
include_usage	bool	是否在回复中包含信用使用信息。	False	
​
回复格式
您收到的响应对象将采用以下格式：
钥匙	类型	描述
results	list[Result]	按相关性排序的搜索结果列表。
query	str	您的搜索查询。
response_time	float	您的搜索结果响应时间。
answer（选修的）	str	这是由 LLM 根据 Tavily 的搜索结果生成的搜索查询答案。仅当include_answer设置为时才可用True。
images（选修的）	list[str]或者list[ImageResult]	include_images仅当设置为时才可用True。查询相关的图像 URL 列表。如果include_image_descriptions设置为True，则每个条目都将是一个ImageResult。当include_images设置为时True，中的每个结果results还将包含其自身的images列表，其中包含从该特定来源提取的图像。
request_id	str	您可以与客户支持部门共享一个唯一的请求标识符，以帮助解决特定请求的问题。
​
结果
Key	Type	描述
title	str	搜索结果的标题。
url	str	搜索结果的网址。
content	str	从抓取的 URL 中提取与查询最相关的内容。Tavily 使用其专有的 AI 技术，根据上下文质量和大小提取最相关的内容。
score	float	搜索结果的相关性得分。
raw_content（选修的）	str	网站的已解析和清理的 HTML 内容。仅当include_raw_content设置为时才可用True。
published_date（选修的）	str	来源的出版日期。仅当搜索topic设置为“.”时，此信息才可用"news"。
favicon（选修的）	str	搜索结果的网站图标网址。
images（选修的）	list[str]或者list[ImageResult]	从此搜索结果中提取的图像。仅当include_images设置为时包含True。如果include_image_descriptions设置为True，则每个条目都将是一个ImageResult。
​
图片结果
如果includeImageDescriptions设置为true，则列表中的每张图片images都将采用以下ImageResult格式：
钥匙	类型	描述
url	string	图片的网址。
description	string	由 LLM 生成的图像描述。
​
例子
要求

回复

​
完全匹配示例
exact_match在查询中使用带引号的短语，可以查找包含特定名称或短语的完整结果：
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")

response = client.search(
    query='"John Smith" CEO Acme Corp',
    exact_match=True
)


# 爬虫功能，这个工具需要谨慎使用，因为比较消耗额度
您可以通过 Python 中的crawl函数访问 Tavily Crawl。
​
参数
范围	类型	描述	默认
url （必需的）	str	要开始爬取的根 URL。	—
max_depth	int	最大抓取深度。定义爬虫可以从基本 URL 开始抓取的最大范围。	1
max_breadth	int	树状结构每一层（即每一页）可跟踪的最大链接数。	20
limit	int	爬虫停止前将处理的链接总数。	50
instructions	str	爬虫的自然语言指令。	—
select_paths	list[str]	使用正则表达式模式仅选择具有特定路径模式的 URL（例如"/docs/.*"，，"/api/v1.*"）。	None
select_domains	list[str]	用于选择爬取特定域或子域的正则表达式模式"^docs\.example\.com$"（例如， ）。	None
exclude_paths	list[str]	使用正则表达式模式排除具有特定路径模式的 URL（例如"/private/.*"，，"/admin/.*"）。	None
exclude_domains	list[str]	正则表达式模式用于排除特定域或子域进行爬取（例如，"^private\.example\.com$"）。	None
allow_external	bool	是否允许点击指向外部域名的链接。	True
include_images	bool	是否从抓取的页面中提取图像 URL。	False
extract_depth	str	高级提取功能可以检索更多数据，包括表格和嵌入式内容，成功率更高，但可能会增加延迟。选项："basic"或"advanced"。	"basic"
format	str	提取的网页内容格式。markdown返回 Markdown 格式的内容。text返回纯文本格式的内容，可能会增加延迟。	"markdown"
include_favicon	bool	是否包含每个搜索结果的网站图标网址。	False
timeout	float	等待爬取操作完成的最长时间（以秒为单位），超过此时间将超时。该值必须介于 10 秒和 150 秒之间。	150
include_usage	bool	是否在响应中包含积分使用信息。NOTE:如果 /extract 和 /map 的总使用量尚未达到最低要求，则该值可能为 0。详情请参阅我们的积分和定价文档。	False
chunks_per_source	int	内容片段是从源中提取的短内容（每个最多 500 个字符）。用于chunks_per_source定义每个源返回的相关内容片段的最大数量，并控制其raw_content长度。内容片段将显示在raw_content字段中，格式为：<chunk 1> [...] <chunk 2> [...] <chunk 3>。值必须介于 1 和 5 之间。	3
​
回复格式
您收到的响应对象将采用以下格式：
钥匙	类型	描述
base_url	str	您开始爬取操作的 URL。
results	list[Result]	已抓取页面的列表。
response_time	float	爬虫响应时间。
request_id	str	您可以与客户支持部门共享一个唯一的请求标识符，以帮助解决特定请求的问题。
​
结果
列表中每个成功结果results都将采用以下Result格式：
钥匙	类型	描述
url	str	网页的网址。
raw_content	str	提取的原始内容物。
images	list[str]	从页面中提取的图片URL。
favicon（选修的）	str	搜索结果的网站图标网址。
​
例子
要求

from tavily import TavilyClient

# Step 1. Instantiating your TavilyClient
tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")

# Step 2. Defining the starting URL of the crawl
url = "https://docs.tavily.com"

# Step 3. Executing the crawl with some guidance parameters
response = tavily_client.crawl(url, instructions="Find information on the Python SDK")

# Step 4. Printing the crawled results
print(response)
回复

{
    "base_url": "https://docs.tavily.com",
    "results": [
        {
            "url": "https://docs.tavily.com/sdk/python/quick-start",
            "raw_content": "Quickstart - Tavily Docs\n\n[Tavily Docs home page![light logo](https://mintlify.s3.us-west-1.amazonaws.com/tavilyai/logo/light.svg)![dark logo](https://mintlify.s3.us-west-1.amazonaws.com/tavilyai/logo/dark.svg)](https://tavily.com/)\n\nSearch or ask...\n\nCtrl K\n\n- [Support](mailto:support@tavily.com)\n- [Get an API key](https://app.tavily.com)\n- [Get an API key](https://app.tavily.com)\n\nSearch...\n\nNavigation\n\nPython\n\nQuickstart\n\n[Home](/welcome)[Documentation](/documentation/about)[SDKs](/sdk/python/quick-start)[Examples](/examples/use-cases/data-enrichment)[FAQ](/faq/faq)\n\n- [API Playground](https://app.tavily.com/playground)\n- [Community](https://community.tavily.com)\n- [Blog](https://blog.tavily.com)\n\n##### Python\n\n- [Quickstart](/sdk/python/quick-start)\n- [SDK Reference](/sdk/python/reference)\n\n##### JavaScript\n\n- [Quickstart](/sdk/javascript/quick-start)\n- [SDK Reference](/sdk/javascript/reference)\n\nPython\n\n# Quickstart\n\nIntegrate Tavily\u2019s powerful APIs natively in your Python apps.\n\nLooking for the Python SDK Reference? Head to our [Python SDK Reference](/sdk/python/reference) and learn how to use `tavily-python`.\n\n## [\u200b](#introduction) Introduction\n\nThe Python SDK allows for easy interaction with the Tavily API, offering the full range of our search functionality directly from your Python programs. Easily integrate smart search capabilities into your applications, harnessing Tavily\u2019s powerful search features.\n\n[## GitHub\n\n`/tavily-ai/tavily-python`\n\n![GitHub Repo stars](https://img.shields.io/github/stars/tavily-ai/tavily-python?style=social)](https://github.com/tavily-ai/tavily-python)[## PyPI\n\n`tavily-python`\n\n![PyPI downloads](https://img.shields.io/pypi/dm/tavily-python)](https://pypi.org/project/tavily-python)\n\n## [\u200b](#quickstart) Quickstart\n\nGet started with our Python SDK in less than 5 minutes!\n\n[## Get your free API key\n\nYou get 1,000 free API Credits every month. **No credit card required.**](https://app.tavily.com)\n\n### [\u200b](#installation) Installation\n\nYou can install the Tavily Python SDK using the following:\n\nCopy\n\n```\npip install tavily-python\n\n```\n\n### [\u200b](#usage) Usage\n\nWith Tavily\u2019s Python SDK, you can search the web in only 4 lines of code:\n\nCopy\n\n```\nfrom tavily import TavilyClient\n\ntavily_client = TavilyClient(api_key=\"tvly-YOUR_API_KEY\")\nresponse = tavily_client.search(\"Who is Leo Messi?\")\n\nprint(response)\n\n```\n\nYou can also easily extract content from URLs:\n\nCopy\n\n```\nfrom tavily import TavilyClient\n\ntavily_client = TavilyClient(api_key=\"tvly-YOUR_API_KEY\")\nresponse = tavily_client.extract(\"https://en.wikipedia.org/wiki/Lionel_Messi\")\n\nprint(response)\n\n```\n\nTavily also allows you to perform a smart crawl starting at a given URL.\n\nCopy\n\n```\nfrom tavily import TavilyClient\n\ntavily_client = TavilyClient(api_key=\"tvly-YOUR_API_KEY\")\nresponse = tavily_client.crawl(\"https://docs.tavily.com\", query=\"Python SDK\")\n\nprint(response)\n\n```\n\nThese examples are very simple, and you can do so much more with Tavily!\n\n## [\u200b](#features) Features\n\nOur Python SDK supports the full feature range of our [REST API](/api-reference), and more. We offer both a synchronous and an asynchronous client, for increased flexibility.\n\n- The `search` function lets you harness the full power of Tavily Search.\n- The `extract` function allows you to easily retrieve web content with Tavily Extract.\n\nFor more details, head to the [Python SDK Reference](/sdk/python/reference).\n\n[SDK Reference](/sdk/python/reference)\n\n[x](https://x.com/tavilyai)[github](https://github.com/tavily-ai)[linkedin](https://linkedin.com/company/tavily)[website](https://tavily.com)\n\n[Powered by Mintlify](https://mintlify.com/preview-request?utm_campaign=poweredBy&utm_medium=docs&utm_source=docs.tavily.com)\n\nOn this page\n\n- [Introduction](#introduction)\n- [Quickstart](#quickstart)\n- [Installation](#installation)\n- [Usage](#usage)\n- [Features]\n        }\n    ],\n    'response_time': 9.14\n}\n\n```\n\n## [\u200b](#tavily-map) Tavily Map\n\nTavily Map allows you to obtain a sitemap starting from a base URL.\n\nYou can access Tavily Map in Python through the `map` function.\n\n### [\u200b](#parameters-4) Parameters\n\n| Parameter | Type | Description | Default |\n| --- | --- | --- | --- |\n| `url` **(required)** | `str` | The root URL to begin the mapping. | \u2014 |\n| `max_depth` | `int` | Max depth of the mapping. Defines how far from the base URL the crawler can explore. | `1` |\n| `max_breadth` | `int` | Max number of links to follow **per level** of the tree (i.e., per page). | `20` |\n| `limit` | `int` | Total number of links the crawler will process before stopping. | `50` |\n| `query` | `str` | Natural language instructions for the crawler | \u2014 |\n| `select_paths` | `list[str]` | **Regex patterns** to select only URLs with specific path patterns (e.g., `\"/docs/.*\"`, `\"/api/v1.*\"`). | `None` |\n| `select_domains` | `list[str]` | **Regex patterns** to select crawling to specific domains or subdomains (e.g., `\"^docs\\.example\\.com$\"`). | `None` |\n| `exclude_paths` | `list[str]` | **Regex patterns** to exclude URLs with specific path patterns (e.g., `\"/private/.*\"`, `\"/admin/.*\"`). | `None` |\n| `exclude_domains` | `list[str]` | **Regex patterns** to exclude specific domains or subdomains from crawling (e.g., `\"^private\\.example\\.com$\"`). | `None` |\n| `allow_external` | `bool` | Whether to allow following links that go to external domains. | `False` |\n\n### [\u200b](#response-format-4) Response format\n\nThe response object you receive will be in the following format:\n\n| Key | Type | Description |\n| --- | --- | --- |\n| `base_url` | `str` | The URL you started the mapping from. |\n| `results` | `list[str]` | A list of URLs that were discovered during the mapping. |\n| `response_time` | `float` | The mapping response time. |\n\n### [\u200b](#example-4) Example\n\nRequest\n\nCopy\n\n```\nfrom tavily import TavilyClient\n\n# Step 1. Instantiating your TavilyClient\ntavily_client = TavilyClient(api_key=\"tvly-YOUR_API_KEY\")\n\n# Step 2. Defining the starting URL of the mapping\nurl = \"https://docs.tavily.com\"\n\n# Step 3. Executing the mapping with some guidance parameters\nresponse = tavily_client.mapping(url, query=\"JavaScript\")\n\n# Step 4. Printing the results\nprint(response)\n\n```\n\nResponse\n\nCopy\n\n```\n{\n    'base_url': 'https://docs.tavily.com',\n    'results': [\n      'https://docs.tavily.com/sdk/javascript/quick-start',\n      'https://docs.tavily.com/sdk/javascript/reference',\n    ],\n    'response_time': 8.43\n}\n\n```\n\n## [\u200b](#tavily-hybrid-rag) Tavily Hybrid RAG\n\nTavily Hybrid RAG is an extension of the Tavily Search API built to retrieve relevant data from both the web and an existing database collection. This way, a RAG agent can combine web sources and locally available data to perform its tasks. Additionally, data queried from the web that is not yet in the database can optionally be inserted into it. This will allow similar searches in the future to be answered faster, without the need to query the web again.\n\n### [\u200b](#parameters-5) Parameters\n\nThe TavilyHybridClient class is your gateway to Tavily Hybrid RAG. There are a few important parameters to keep in mind when you are instantiating a Tavily Hybrid Client.\n\n| Parameter | Type | Description | Default |\n| --- | --- | --- | --- |\n| `api_key` | `str` | Your Tavily API Key |  |\n| `db_provider` | `str` | Your database provider. Currently, only `\"mongodb\"` is supported. |  |\n| `collection` | `str` | A reference to the MongoDB collection that will be used for local search. |  |\n| `embeddings_field` (optional) | `str` | The name of the field that stores the embeddings in the specified collection. This field MUST be the same one used in the specified index. This will also be used when inserting web search results in the database using our default function. | `\"embeddings\"` |\n| `content_field` (optional) | `str` | The name of the field that stores the text content in the specified collection. This will also be used when inserting web search results in the database using our default function. | `\"content\"` |\n| `embedding_function` (optional) | `function` | A custom embedding function (if you want to use one). The function must take in a `list[str]` corresponding to the list of strings to be embedded, as well as an additional string defining the type of document. It must return a `list[list[float]]`, one embedding per input string. If no function is provided, defaults to Cohere\u2019s Embed. Keep in mind that you shouldn\u2019t mix different embeddings in the same database collection. |  |\n| `ranking_function` (optional) | `function` | A custom ranking function (if you want to use one). If no function is provided, defaults to Cohere\u2019s Rerank. It should return an ordered `list[dict]` where the documents are sorted by decreasing relevancy to your query. Each returned document will have two properties - `content`, which is a `str`, and `score`, which is a `float`. The function MUST accept the following parameters: `query`: `str` - This is the query you are executing. When your ranking function is called during Hybrid RAG, the query parameter of your search call (more details below) will be passed as query. `documents`:`List[Dict]`: - This is the list of documents that are returned by your Hybrid RAG call and that you want to sort. Each document will have two properties - `content`, which is a `str`, and `score`, which is a `float`. `top_n`: `int` - This is the number of results you want to return after ranking. When your ranking function is called during Hybrid RAG, the max\\_results value will be passed as `top_n`. |  |\n\n### [\u200b](#methods) Methods\n\n`search`(query, max\\_results=10, max\\_local=None, max\\_foreign=None, save\\_foreign=False, \\*\\*kwargs)\n\nPerforms a Tavily Hybrid RAG query and returns the retrieved documents as a `list[dict]` where the documents are sorted by decreasing relevancy to your query. Each returned document will have three properties - `content` (str), `score` (float), and `origin`, which is either `local` or `foreign`.\n\n| Parameter | Type | Description | Default |  |\n| --- | --- | --- | --- | --- |\n| `query` | `str` | The query you want to search for. |  |  |\n| `max_results` | `int` | The maximum number of total search results to return. | 10 |  |\n| `max_local` | `int` | The maximum number of local search results to return. | `None`, which defaults to `max_results`. |  |\n| `max_local` | `int` | The maximum number of local search results to return. | `None`, which defaults to `max_results`. |  |\n| `max_foreign` | `int` | The maximum number of web search results to return. | `None`, which defaults to `max_results`. |  |\n| `save_foreign` | `Union[bool, function]` | Save documents from the web search in the local database. If `True` is passed, our default saving function (which only saves the content `str` and the embedding `list[float]` will be used.) If `False` is passed, no web search result documents will be saved in the local database. If a function is passed, that function MUST take in a `dict` as a parameter, and return another `dict`. The input `dict` contains all properties of the returned Tavily result object. The output dict is the final document that will be inserted in the database. You are free to add to it any fields that are supported by the database, as well as remove any of the default ones. If this function returns `None`, the document will not be saved in the database. |  |  |\n\nAdditional parameters can be provided as keyword arguments (detailed below). The keyword arguments supported by this method are: `search_depth`, `topic`, `include_raw_content`, `include_domains`,`exclude_domains`.\n\n### [\u200b](#setup) Setup\n\n#### [\u200b](#mongodb-setup) MongoDB setup\n\nYou will need to have a MongoDB collection with a vector search index. You can follow the [MongoDB Documentation](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-type/) to learn how to set this up.\n\n#### [\u200b](#cohere-api-key) Cohere API Key\n\nBy default, embedding and ranking use the Cohere API, our recommended option. Unless you want to provide a custom embedding and ranking function, you\u2019ll need to get an API key from [Cohere](https://cohere.com/) and set it as an environment variable named `CO_API_KEY`\n\nIf you decide to stick with Cohere, please note that you\u2019ll need to install the Cohere Python package as well:\n\nCopy\n\n```\npip install cohere\n\n```\n\n#### [\u200b](#tavily-hybrid-rag-client-setup) Tavily Hybrid RAG Client setup\n\nOnce you are done setting up your database, you\u2019ll need to create a MongoDB Client as well as a Tavily Hybrid RAG Client.\nA minimal setup would look like this:\n\nCopy\n\n```\nfrom pymongo import MongoClient\nfrom tavily import TavilyHybridClient\n\ndb = MongoClient(\"mongodb+srv://YOUR_MONGO_URI\")[\"YOUR_DB\"]\n\nhybrid_rag = TavilyHybridClient(\n    api_key=\"tvly-YOUR_API_KEY\",\n    db_provider=\"mongodb\",\n    collection=db.get_collection(\"YOUR_COLLECTION\"),\n    index=\"YOUR_VECTOR_SEARCH_INDEX\",\n    embeddings_field=\"YOUR_EMBEDDINGS_FIELD\",\n    content_field=\"YOUR_CONTENT_FIELD\"\n)\n\n```\n\n### [\u200b](#usage) Usage\n\nOnce you create the proper clients, you can easily start searching. A few simple examples are shown below. They assume you\u2019ve followed earlier steps. You can use most of the Tavily Search parameters with Tavily Hybrid RAG as well.\n\n#### [\u200b](#simple-tavily-hybrid-rag-example) Simple Tavily Hybrid RAG example\n\nThis example will look for context about Leo Messi on the web and in the local database.\nHere, we get 5 sources, both from our database and from the web, but we want to exclude unwanted-domain.com from our web search results:\n\nCopy\n\n```\nresults = hybrid_rag.search(\"Who is Leo Messi?\", max_results=5, exclude_domains=['unwanted-domain.com'])\n\n```\n\nHere, we want to prioritize the number of local sources, so we will get 2 foreign (web) sources, and 5 sources from our database:\n\nCopy\n\n```\nresults = hybrid_rag.search(\"Who is Leo Messi?\",  max_local=5, max_foreign=2)\n\n```\n\nNote: The sum of `max_local` and `max_foreign` can exceed `max_results`, but only the top `max_results` results will be returned.\n\n#### [\u200b](#adding-retrieved-data-to-the-database) Adding retrieved data to the database\n\nIf you want to add the retrieved data to the database, you can do so by setting the save\\_foreign parameter to True:\n\nCopy\n\n```\nresults = hybrid_rag.search(\"Who is Leo Messi?\", save_foreign=True)\n\n```\n\nThis will use our default saving function, which stores the content and its embedding.\n\n### [\u200b](#examples) Examples\n\n#### [\u200b](#sample-1%3A-using-a-custom-saving-function) Sample 1: Using a custom saving function\n\nYou might want to add some extra properties to documents you\u2019re inserting or even discard some of them based on custom criteria. This can be done by passing a function to the save\\_foreign parameter:\n\nCopy\n\n```\ndef save_document(document):\n    if document['score'] < 0.5:\n        return None # Do not save documents with low scores\n\n    return {\n        'content': document['content'],\n\n         # Save the title and URL in the database\n        'site_title': document['title'],\n        'site_url': document['url'],\n\n        # Add a new field\n        'added_at': datetime.now()\n    }\n\nresults = hybrid_rag.search(\"Who is Leo Messi?\", save_foreign=save_document)\n\n```\n\n#### [\u200b](#sample-2%3A-using-a-custom-embedding-function) Sample 2: Using a custom embedding function\n\nBy default, we use [Cohere](https://cohere.com/) for our embeddings. If you want to use your own embeddings, can pass a custom embedding function to the TavilyHybridClient:\n\nCopy\n\n```\ndef my_embedding_function(texts, doc_type): # doc_type will be either 'search_query' or 'search_document'\n    return my_embedding_model.encode(texts)\n\nhybrid_rag = TavilyHybridClient(\n    # ...\n    embedding_function=my_embedding_function\n)\n\n```\n\n#### [\u200b](#sample-3%3A-using-a-custom-ranking-function) Sample 3: Using a custom ranking function\n\nCohere\u2019s [rerank](https://cohere.com/rerank) model is used by default, but you can pass your own function to the ranking\\_function parameter:\n\nCopy\n\n```\ndef my_ranking_function(query, documents, top_n):\n    return my_ranking_model.rank(query, documents, top_n)\n\nhybrid_rag = TavilyHybridClient(\n    # ...\n    ranking_function=my_ranking_function\n)\n\n```\n\n[Quickstart](/sdk/python/quick-start)[Quickstart](/sdk/javascript/quick-start)\n\n[x](https://x.com/tavilyai)[github](https://github.com/tavily-ai)[linkedin](https://linkedin.com/company/tavily)[website](https://tavily.com)\n\n[Powered by Mintlify](https://mintlify.com/preview-request?utm_campaign=poweredBy&utm_medium=docs&utm_source=docs.tavily.com)\n\nOn this page\n\n- [Instantiating a client](#instantiating-a-client)\n- [Synchronous Client](#synchronous-client)\n- [Asynchronous Client](#asynchronous-client)\n- [Proxies](#proxies)\n- [Tavily Search](#tavily-search)\n- [Parameters](#parameters)\n- [Response format](#response-format)\n- [Results](#results)\n- [Image Results](#image-results)\n- [Example](#example)\n- [Tavily Extract](#tavily-extract)\n- [Parameters](#parameters-2)\n- [Response format](#response-format-2)\n- [Successful Results](#successful-results)\n- [Failed Results](#failed-results)\n- [Example](#example-2)\n- [Tavily Crawl](#tavily-crawl)\n- [Parameters](#parameters-3)\n- [Response format](#response-format-3)\n- [Results](#results-2)\n- [Example](#example-3)\n- [Tavily Map](#tavily-map)\n- [Parameters](#parameters-4)\n- [Response format](#response-format-4)\n- [Example](#example-4)\n- [Tavily Hybrid RAG](#tavily-hybrid-rag)\n- [Parameters](#parameters-5)\n- [Methods](#methods)\n- [Setup](#setup)\n- [MongoDB setup](#mongodb-setup)\n- [Cohere API Key](#cohere-api-key)\n- [Tavily Hybrid RAG Client setup](#tavily-hybrid-rag-client-setup)\n- [Usage](#usage)\n- [Simple Tavily Hybrid RAG example](#simple-tavily-hybrid-rag-example)\n- [Adding retrieved data to the database](#adding-retrieved-data-to-the-database)\n- [Examples](#examples)\n- [Sample 1: Using a custom saving function](#sample-1%3A-using-a-custom-saving-function)\n- [Sample 2: Using a custom embedding function](#sample-2%3A-using-a-custom-embedding-function)\n- [Sample 3: Using a custom ranking function](#sample-3%3A-using-a-custom-ranking-function)",
            "images": [],
            "favicon": "https://mintlify.s3-us-west-1.amazonaws.com/tavilyai/_generated/favicon/apple-touch-icon.png?v=3"

        }
    ],
    "response_time": 9.07,
    "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
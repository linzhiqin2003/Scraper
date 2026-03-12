from web_scraper.sources.sina.scrapers.search import SearchScraper


HTML = """
<html>
  <body>
    <div class="l_v2">找到相关新闻269篇</div>
    <div class="box-result clearfix">
      <h2><a href="https://example.com/article-1">楼市资本论 | 第一篇</a></h2>
      <div class="r-img"><img class="left_img" src="https://example.com/1.jpg" /></div>
      <div class="r-info">
        <p class="content">第一篇摘要。</p>
        <h2><span class="fgray_time">楼市资本论   2018-12-25 14:08:01</span></h2>
      </div>
    </div>
    <div class="box-result clearfix">
      <h2><a href="/article-2">楼市资本论 | 第二篇</a></h2>
      <div class="r-info">
        <p class="content">第二篇摘要。</p>
        <h2><span class="fgray_time">财经头条   2018-12-24 16:37:51</span></h2>
      </div>
    </div>
    <div class="pagebox">
      <a title="第2页">2</a>
      <a title="第3页">3</a>
      <a title="下一页">下一页</a>
    </div>
  </body>
</html>
"""


def test_parse_page_extracts_results_and_pagination() -> None:
    parsed = SearchScraper._parse_page(HTML)

    assert parsed.total_results == 269
    assert parsed.max_page == 3
    assert len(parsed.results) == 2

    first = parsed.results[0]
    assert first.title == "楼市资本论 | 第一篇"
    assert first.url == "https://example.com/article-1"
    assert first.snippet == "第一篇摘要。"
    assert first.source_name == "楼市资本论"
    assert first.published_at == "2018-12-25 14:08:01"
    assert first.image_url == "https://example.com/1.jpg"

    second = parsed.results[1]
    assert second.url == "https://search.sina.com.cn/article-2"
    assert second.source_name == "财经头条"

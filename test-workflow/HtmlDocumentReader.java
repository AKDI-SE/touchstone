/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import net.dankito.readability4j.Readability4J;
import net.dankito.readability4j.Article;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.nodes.Node;
import org.jsoup.nodes.TextNode;
import org.jsoup.select.Elements;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Prod-profile {@link DocumentReader} for public-web HTML.
 *
 * <p>Stack (per the design doc §3.3):
 * <ul>
 *   <li>JDK {@link HttpClient} to fetch HTML — no third-party HTTP library.</li>
 *   <li>{@code org.jsoup:jsoup} for DOM cleaning / query.</li>
 *   <li>{@code net.dankito.readability4j} (Mozilla Readability Java port) for body extraction.</li>
 * </ul>
 *
 * <p><b>Key constraints:</b>
 * <ul>
 *   <li>SPA detection: many LLM-vendor pricing pages are React/Vue-rendered. When jsoup
 *       fetches an empty shell (正文极短 / 只剩空 div), this reader returns
 *       {@code doc_type=spa_blocked} so the root agent can switch source instead of
 *       silently emitting empty content.</li>
 *   <li>Access-restricted pages (Cloudflare 403 / 429 / 5xx) return
 *       {@code doc_type=cloudflare_403} (or {@code other} for non-Cloudflare 5xx) with
 *       an empty body.</li>
 * </ul>
 */
public final class HtmlDocumentReader implements DocumentReader {

    private static final Logger LOG = LoggerFactory.getLogger(HtmlDocumentReader.class);

    /** Minimum extracted-text length (chars) to be considered real content. Below this → spa_blocked. */
    static final int MIN_CONTENT_LENGTH = 200;

    private static final Duration DEFAULT_CONNECT_TIMEOUT = Duration.ofSeconds(10);
    private static final Duration DEFAULT_REQUEST_TIMEOUT = Duration.ofSeconds(20);

    private static final String USER_AGENT =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    + "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

    private final HttpClient httpClient;
    private final Duration requestTimeout;

    public HtmlDocumentReader() {
        this(DEFAULT_CONNECT_TIMEOUT, DEFAULT_REQUEST_TIMEOUT);
    }

    public HtmlDocumentReader(Duration connectTimeout, Duration requestTimeout) {
        this.requestTimeout = requestTimeout == null ? DEFAULT_REQUEST_TIMEOUT : requestTimeout;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout == null ? DEFAULT_CONNECT_TIMEOUT : connectTimeout)
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    @Override
    public ReadDocument read(String url, String focusQuestion) {
        if (url == null || url.isBlank()) {
            return ReadDocument.blocked("other");
        }

        HttpResponse<String> resp;
        try {
            resp = fetch(url);
        } catch (IOException | InterruptedException e) {
            LOG.warn("read_url: fetch failed for {}: {}", url, e.toString());
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return ReadDocument.blocked("other");
        }

        int status = resp.statusCode();
        if (isBlockedStatus(status)) {
            String kind = isCloudflareBlocked(resp, status) ? "cloudflare_403" : "other";
            LOG.info("read_url: access-restricted status={} url={} kind={}", status, url, kind);
            return ReadDocument.blocked(kind);
        }
        if (status >= 400) {
            LOG.info("read_url: http error status={} url={}", status, url);
            return ReadDocument.blocked("other");
        }

        String html = resp.body();
        if (html == null || html.isBlank()) {
            return ReadDocument.blocked("spa_blocked");
        }
        return parseHtml(url, html);
    }

    /** Network-free extraction entry point — used by tests and the stub reader. */
    ReadDocument parseHtml(String url, String html) {
        Document doc;
        try {
            doc = Jsoup.parse(html, url);
        } catch (RuntimeException e) {
            LOG.warn("read_url: jsoup parse failed for {}: {}", url, e.toString());
            return ReadDocument.blocked("other");
        }

        Article article;
        try {
            Readability4J r = new Readability4J(url, html);
            article = r.parse();
        } catch (RuntimeException e) {
            LOG.warn("read_url: readability4j failed for {}: {}", url, e.toString());
            article = null;
        }

        String title = article != null && article.getTitle() != null && !article.getTitle().isBlank()
                ? article.getTitle().trim()
                : (doc.title() == null ? "" : doc.title().trim());

        String contentText = article != null && article.getTextContent() != null
                ? article.getTextContent().trim()
                : "";

        // SPA detection: readability found nothing meaningful and the raw DOM has very little text.
        if (contentText.length() < MIN_CONTENT_LENGTH) {
            int rawTextLen = rawVisibleTextLength(doc);
            if (rawTextLen < MIN_CONTENT_LENGTH) {
                LOG.info("read_url: spa_blocked url={} readabilityTextLen={} rawTextLen={}",
                        url, contentText.length(), rawTextLen);
                return ReadDocument.blocked("spa_blocked");
            }
            // readability failed but the raw page has text — fall back to raw text.
            contentText = visibleText(doc);
        }

        List<ReadDocument.Section> sections = extractSections(doc, article);
        String author = extractAuthor(doc, article);
        String publishDate = extractPublishDate(doc);
        String docType = classifyDocType(url, doc);

        // Summary is generated by the LLM in the ReAct loop, not here.
        return new ReadDocument(
                title,
                contentText,
                sections,
                "",
                author,
                publishDate,
                docType);
    }

    private HttpResponse<String> fetch(String url) throws IOException, InterruptedException {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(requestTimeout)
                .header("User-Agent", USER_AGENT)
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                .GET()
                .build();
        return httpClient.send(req, HttpResponse.BodyHandlers.ofString());
    }

    private static boolean isBlockedStatus(int status) {
        return status == 401 || status == 403 || status == 429 || status >= 500;
    }

    private static boolean isCloudflareBlocked(HttpResponse<String> resp, int status) {
        String server = resp.headers().firstValue("server").orElse("").toLowerCase(Locale.ROOT);
        boolean hasCfRay = resp.headers().firstValue("cf-ray").isPresent();
        return (status == 403 || status == 429 || status == 503)
                && (server.contains("cloudflare") || hasCfRay);
    }

    private static int rawVisibleTextLength(Document doc) {
        return doc.body() == null ? 0 : visibleText(doc).length();
    }

    private static String visibleText(Document doc) {
        Document clone = doc.clone();
        clone.select("script,style,noscript,svg,iframe,header,footer,nav,form,button").remove();
        String t = clone.body() == null ? "" : clone.body().text();
        return t == null ? "" : t.trim();
    }

    private static List<ReadDocument.Section> extractSections(Document doc, Article article) {
        Elements headings;
        String contentHtml = article != null && article.getContent() != null ? article.getContent() : "";
        if (!contentHtml.isBlank()) {
            headings = Jsoup.parse(contentHtml).select("h1,h2,h3");
        } else {
            headings = doc.select("main h1,main h2,main h3,article h1,article h2,article h3");
        }
        if (headings.isEmpty()) {
            return List.of();
        }
        Set<String> seen = new LinkedHashSet<>();
        List<ReadDocument.Section> out = new ArrayList<>();
        for (Element h : headings) {
            String heading = h.text() == null ? "" : h.text().trim();
            if (heading.isBlank() || !seen.add(heading)) {
                continue;
            }
            StringBuilder body = new StringBuilder();
            Node n = h.nextSibling();
            int guard = 0;
            while (n != null && guard < 2000) {
                guard++;
                if (n instanceof Element el && isHeading(el)) {
                    break;
                }
                if (n instanceof TextNode tn && !tn.text().isBlank()) {
                    body.append(tn.text()).append(' ');
                } else if (n instanceof Element el) {
                    String t = el.text();
                    if (!t.isBlank()) {
                        body.append(t).append(' ');
                    }
                }
                n = n.nextSibling();
            }
            String bodyText = body.toString().trim();
            if (!bodyText.isEmpty()) {
                out.add(new ReadDocument.Section(heading, bodyText));
            }
        }
        return out.isEmpty() ? List.of() : out;
    }

    private static boolean isHeading(Element el) {
        String tag = el.tagName();
        return "h1".equals(tag) || "h2".equals(tag) || "h3".equals(tag) || "h4".equals(tag);
    }

    private static String extractAuthor(Document doc, Article article) {
        String author = article != null && article.getByline() != null ? article.getByline().trim() : null;
        if ((author == null || author.isBlank())) {
            Elements meta = doc.select("meta[name=author]");
            if (!meta.isEmpty()) {
                author = meta.first().attr("content").trim();
            }
        }
        return (author == null || author.isBlank()) ? null : author;
    }

    private static String extractPublishDate(Document doc) {
        for (String sel : new String[]{
                "meta[property=article:published_time]",
                "meta[name=pubdate]",
                "meta[name=publishdate]",
                "meta[name=date]",
                "time[datetime]"}) {
            Elements e = doc.select(sel);
            if (!e.isEmpty()) {
                String v = "time".equals(e.first().tagName())
                        ? e.first().attr("datetime")
                        : e.first().attr("content");
                if (v != null && !v.isBlank()) {
                    return v.trim();
                }
            }
        }
        return null;
    }

    private static String classifyDocType(String url, Document doc) {
        String host = hostOf(url);
        String lowerUrl = url.toLowerCase(Locale.ROOT);
        String title = doc.title() == null ? "" : doc.title().toLowerCase(Locale.ROOT);
        boolean isVendorHost = host.contains("volcengine") || host.contains("bailian")
                || host.contains("bigmodel") || host.contains("moonshot")
                || host.contains("deepseek") || host.contains("cloud.baidu")
                || host.contains("cloud.tencent");
        boolean isPricePage = title.contains("定价") || title.contains("price") || title.contains("计费")
                || lowerUrl.contains("price") || lowerUrl.contains("billing");
        if (isVendorHost) {
            return isPricePage ? "pricing_page" : "doc";
        }
        if (isPricePage) {
            return "pricing_page";
        }
        if (doc.selectFirst("article") != null) {
            return "blog";
        }
        Elements metaType = doc.select("meta[property=og:type]");
        if (!metaType.isEmpty()) {
            String t = metaType.first().attr("content").toLowerCase(Locale.ROOT);
            if (t.contains("article")) {
                return "blog";
            }
            if (t.contains("news")) {
                return "news";
            }
        }
        return "other";
    }

    private static String hostOf(String url) {
        try {
            return URI.create(url).getHost() == null ? "" : URI.create(url).getHost().toLowerCase(Locale.ROOT);
        } catch (RuntimeException e) {
            return "";
        }
    }
}

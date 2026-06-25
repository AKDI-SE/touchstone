/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Stub-profile {@link DocumentReader} — no network access.
 *
 * <p>Per the design doc §4.1: routes by the url's host+path to the HTML fixtures under
 * {@code src/main/resources/fixtures/}. Unmatched URLs return {@code doc_type=other}
 * with a warning log, so the root agent's integration test can verify the fallback path.
 *
 * <p>Routing keys (matched by substring on host+path, case-insensitive):
 * <ul>
 *   <li>{@code volcengine} → {@code pricing-volcengine.html}</li>
 *   <li>{@code bailian}    → {@code pricing-bailian.html}</li>
 *   <li>{@code blog} / {@code comparison} / {@code zhihu} / {@code juejin} / {@code csdn} → {@code blog-comparison.html}</li>
 *   <li>{@code spa}        → {@code spa-blocked.html} (returns {@code spa_blocked})</li>
 *   <li>{@code cloudflare} → {@code cloudflare-403.html} (returns {@code cloudflare_403})</li>
 * </ul>
 */
public final class StubDocumentReader implements DocumentReader {

    private static final Logger LOG = LoggerFactory.getLogger(StubDocumentReader.class);

    static final String FIXTURES_DIR = "/fixtures/";

    private final HtmlDocumentReader parser = new HtmlDocumentReader();

    @Override
    public ReadDocument read(String url, String focusQuestion) {
        if (url == null || url.isBlank()) {
            return ReadDocument.blocked("other");
        }
        String key = hostPlusPath(url).toLowerCase(Locale.ROOT);

        if (key.contains("spa")) {
            // The fixture itself is an SPA shell; the parser will detect spa_blocked.
            String html = loadFixture("spa-blocked.html");
            return parser.parseHtml(url, html);
        }
        if (key.contains("cloudflare")) {
            return ReadDocument.blocked("cloudflare_403");
        }
        if (key.contains("volcengine") || key.contains("ark")) {
            return parser.parseHtml(url, loadFixture("pricing-volcengine.html"));
        }
        if (key.contains("bailian") || key.contains("aliyun")) {
            return parser.parseHtml(url, loadFixture("pricing-bailian.html"));
        }
        if (key.contains("blog") || key.contains("comparison") || key.contains("zhihu")
                || key.contains("juejin") || key.contains("csdn")) {
            return parser.parseHtml(url, loadFixture("blog-comparison.html"));
        }
        LOG.warn("stub read-agent: no fixture matched url={} → returning doc_type=other", url);
        return ReadDocument.blocked("other");
    }

    private static String hostPlusPath(String url) {
        try {
            URI u = URI.create(url);
            String host = u.getHost() == null ? "" : u.getHost();
            String path = u.getPath() == null ? "" : u.getPath();
            return host + path;
        } catch (RuntimeException e) {
            return url;
        }
    }

    static String loadFixture(String name) {
        String path = FIXTURES_DIR + name;
        try (InputStream is = StubDocumentReader.class.getResourceAsStream(path)) {
            if (is == null) {
                throw new IllegalStateException("fixture not found: " + path);
            }
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to load fixture: " + path, e);
        }
    }
}

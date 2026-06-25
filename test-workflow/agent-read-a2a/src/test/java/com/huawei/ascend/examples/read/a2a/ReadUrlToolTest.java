/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for {@link StubDocumentReader} + {@link ReadUrlTool} covering the three
 * contract paths required by the design doc §4.2: a pricing page, a spa_blocked page,
 * and a cloudflare_403 page. Also covers the unmatched-URL fallback (doc_type=other).
 */
class ReadUrlToolTest {

    @Test
    void stubReaderServesVolcenginePricingFixture() {
        StubDocumentReader reader = new StubDocumentReader();
        DocumentReader.ReadDocument doc = reader.read(
                "https://www.volcengine.com/docs/240/pricing", "豆包 Pro 4K 输入价格");

        assertThat(doc.docType()).isEqualTo("pricing_page");
        assertThat(doc.title()).contains("定价");
        assertThat(doc.contentMarkdown()).contains("0.0008");
        assertThat(doc.author()).isEqualTo("火山引擎");
        assertThat(doc.publishDate()).isEqualTo("2026-03-15");
    }

    @Test
    void stubReaderDetectsSpaBlocked() {
        StubDocumentReader reader = new StubDocumentReader();
        DocumentReader.ReadDocument doc = reader.read(
                "https://spa.bigmodel.cn/pricing", null);

        assertThat(doc.docType()).isEqualTo("spa_blocked");
        assertThat(doc.contentMarkdown()).isEmpty();
    }

    @Test
    void stubReaderReturnsCloudflare403ForCloudflareHost() {
        StubDocumentReader reader = new StubDocumentReader();
        DocumentReader.ReadDocument doc = reader.read(
                "https://cloudflare-protected.example.com/secret", null);

        assertThat(doc.docType()).isEqualTo("cloudflare_403");
        assertThat(doc.contentMarkdown()).isEmpty();
    }

    @Test
    void stubReaderReturnsOtherForUnmatchedUrl() {
        StubDocumentReader reader = new StubDocumentReader();
        DocumentReader.ReadDocument doc = reader.read(
                "https://random-unknown-host.example.com/page", null);

        assertThat(doc.docType()).isEqualTo("other");
    }

    @Test
    void readUrlToolReturnsSuccessWithMetadataForPricingPage() {
        StubDocumentReader reader = new StubDocumentReader();
        ReadUrlTool tool = new ReadUrlTool(reader);

        Map<String, Object> out = ReadUrlTool.execute(reader,
                Map.of("url", "https://www.volcengine.com/docs/240/pricing"));

        assertThat(out.get("successCode")).isEqualTo(true);
        assertThat(out.get("title")).asString().contains("定价");
        assertThat(out.get("content_markdown")).asString().contains("0.0008");
        @SuppressWarnings("unchecked")
        Map<String, Object> metadata = (Map<String, Object>) out.get("metadata");
        assertThat(metadata.get("doc_type")).isEqualTo("pricing_page");
        assertThat(metadata.get("author")).isEqualTo("火山引擎");
    }

    @Test
    void readUrlToolReturnsFailureForMissingUrl() {
        StubDocumentReader reader = new StubDocumentReader();
        Map<String, Object> out = ReadUrlTool.execute(reader, Map.of());

        assertThat(out.get("successCode")).isEqualTo(false);
        assertThat(out.get("errorMessage")).asString().contains("missing url");
    }

    @Test
    void readUrlToolSurfacesSpaBlockedDocType() {
        StubDocumentReader reader = new StubDocumentReader();
        Map<String, Object> out = ReadUrlTool.execute(reader,
                Map.of("url", "https://spa.bigmodel.cn/pricing"));

        assertThat(out.get("successCode")).isEqualTo(true);
        @SuppressWarnings("unchecked")
        Map<String, Object> metadata = (Map<String, Object>) out.get("metadata");
        assertThat(metadata.get("doc_type")).isEqualTo("spa_blocked");
        assertThat(out.get("content_markdown")).asString().isEmpty();
    }
}

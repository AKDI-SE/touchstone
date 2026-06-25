/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import com.openjiuwen.core.foundation.tool.ToolCard;
import com.openjiuwen.core.foundation.tool.function.LocalFunction;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * <code>read_url</code> tool — fetch a URL and extract its main content.
 *
 * <p>Wraps a {@link DocumentReader} (HtmlDocumentReader in prod, StubDocumentReader in
 * stub profile) as an openJiuwen {@link LocalFunction}. The tool signature matches the
 * A2A skill contract from the design doc §3.3:
 * <pre>
 * input:  { url: string, focus_question: string|null }
 * output: { title, content_markdown, sections[], summary, metadata{ author, publish_date, doc_type } }
 * </pre>
 *
 * <p>Blocked / error results are returned with {@code doc_type=spa_blocked|cloudflare_403|other}
 * and empty content fields, so the root agent can decide to switch source.
 */
public final class ReadUrlTool extends LocalFunction {

    public static final String TOOL_ID = "read_url";

    public ReadUrlTool(DocumentReader reader) {
        super(buildCard(), inputs -> execute(reader, inputs));
    }

    static Map<String, Object> execute(DocumentReader reader, Map<String, Object> inputs) {
        String url = asString(inputs.get("url"));
        String focusQuestion = asString(inputs.get("focus_question"));
        if (url == null || url.isBlank()) {
            return failure("missing url");
        }
        Objects.requireNonNull(reader, "reader");
        DocumentReader.ReadDocument doc;
        try {
            doc = reader.read(url, focusQuestion);
        } catch (RuntimeException e) {
            return failure("read error: " + e.getMessage());
        }
        if (doc == null) {
            return failure("reader returned null");
        }
        return toOutput(doc);
    }

    private static Map<String, Object> toOutput(DocumentReader.ReadDocument doc) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("successCode", true);
        out.put("title", nullToEmpty(doc.title()));
        out.put("content_markdown", nullToEmpty(doc.contentMarkdown()));

        List<Map<String, Object>> sections;
        if (doc.sections() == null || doc.sections().isEmpty()) {
            sections = List.of();
        } else {
            sections = new java.util.ArrayList<>(doc.sections().size());
            for (DocumentReader.ReadDocument.Section s : doc.sections()) {
                Map<String, Object> sec = new LinkedHashMap<>();
                sec.put("heading", nullToEmpty(s.heading()));
                sec.put("body", nullToEmpty(s.body()));
                sections.add(sec);
            }
        }
        out.put("sections", sections);
        out.put("summary", nullToEmpty(doc.summary()));

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("author", doc.author());
        metadata.put("publish_date", doc.publishDate());
        metadata.put("doc_type", nullToEmpty(doc.docType()));
        out.put("metadata", metadata);
        return out;
    }

    private static Map<String, Object> failure(String message) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("successCode", false);
        out.put("title", "");
        out.put("content_markdown", "");
        out.put("sections", List.of());
        out.put("summary", "");
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("author", null);
        metadata.put("publish_date", null);
        metadata.put("doc_type", "other");
        out.put("metadata", metadata);
        out.put("errorMessage", message);
        return out;
    }

    private static String asString(Object v) {
        return v == null ? null : String.valueOf(v);
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }

    private static ToolCard buildCard() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("url", Map.of(
                "type", "string",
                "description", "要抓取的公网 URL（http/https），通常是 search-agent 返回的候选 url"));
        props.put("focus_question", Map.of(
                "type", "string",
                "description", "可选的关注问题；非空时摘要围绕该问题生成。可空"));

        Map<String, Object> inputParams = new HashMap<>();
        inputParams.put("type", "object");
        inputParams.put("properties", props);
        inputParams.put("required", List.of("url"));

        return ToolCard.builder()
                .id(TOOL_ID)
                .name(TOOL_ID)
                .description("抓取公网 HTML 并提取主体内容。检测到 SPA 渲染或访问受限（Cloudflare/4xx/5xx）时返回 doc_type 标记。")
                .inputParams(inputParams)
                .build();
    }
}

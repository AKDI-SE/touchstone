/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import java.util.List;

/**
 * Strategy interface for fetching and extracting content from a document at a URL.
 *
 * <p>Phase 1 ships two implementations:
 * <ul>
 *   <li>{@link HtmlDocumentReader} — prod profile: real HTTP via JDK HttpClient + jsoup/readability4j.</li>
 *   <li>{@link StubDocumentReader} — stub profile: serves fixtures from classpath, no network.</li>
 * </ul>
 * New implementations can cover PDF / 内部知识库 in later phases without changing the
 * {@code read_url} tool surface.
 */
public interface DocumentReader {

    /**
     * Fetch and extract the document at {@code url}.
     *
     * @param url            absolute URL to fetch (http/https)
     * @param focusQuestion  optional focus question; implementations may use it to bias
     *                       the summary toward the question (null/blank = general summary)
     * @return a populated {@link ReadDocument}; never {@code null}. When content cannot
     *         be extracted (SPA / access-restricted / network error), implementations
     *         return a {@link ReadDocument} whose {@link ReadDocument#docType()} is set
     *         to {@code spa_blocked} / {@code cloudflare_403} / {@code other}.
     */
    ReadDocument read(String url, String focusQuestion);

    /** Result DTO mirroring the read-agent design doc §3.3 output contract. */
    record ReadDocument(
            String title,
            String contentMarkdown,
            List<Section> sections,
            String summary,
            String author,
            String publishDate,
            String docType) {

        /** A (heading, body) section extracted from the document. */
        public record Section(String heading, String body) {
        }

        /** Convenience for blocked/error results. */
        public static ReadDocument blocked(String docType) {
            return new ReadDocument("", "", List.of(), "", null, null, docType);
        }
    }
}

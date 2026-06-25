/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * Prompt contract test — mirrors {@code TripPromptContractTest} in agent-trip-a2a.
 */
class ReadPromptContractTest {

    @Test
    void promptInjectsReadToolNameAndToday() {
        String prompt = SystemPromptBuilder.build("read_url");

        assertThat(prompt)
                .contains("read_url")
                .contains("spa_blocked")
                .contains("cloudflare_403")
                .contains("doc_type")
                .contains("focus_question")
                .doesNotContain(ReadAgentConstants.VAR_READ_TOOL_NAME)
                .doesNotContain(ReadAgentConstants.VAR_TODAY);
    }

    @Test
    void defaultBuilderInjectsReadToolName() {
        String prompt = SystemPromptBuilder.build();

        assertThat(prompt)
                .contains("read_url")
                .doesNotContain(ReadAgentConstants.VAR_READ_TOOL_NAME);
    }
}

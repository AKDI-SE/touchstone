/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.ZoneId;

/**
 * 网页阅读智能体的 ReAct system prompt 构造器。
 * <p>Prompt 正文见 {@code src/main/resources/prompts/read-agent-system-prompt.md}。
 *
 * <p>命名与结构与 agent-trip-a2a 的 {@code SystemPromptBuilder} 保持一致。
 */
public final class SystemPromptBuilder {

    private SystemPromptBuilder() {
    }

    /**
     * 加载 markdown 模板并替换动态变量。
     */
    public static String build() {
        return build(ReadAgentConstants.readToolName());
    }

    /**
     * 加载 markdown 模板并替换动态变量。
     *
     * @param readToolName 读取工具名（{@code read_url}）
     */
    public static String build(String readToolName) {
        String prompt = loadResource(ReadAgentConstants.PROMPT_RESOURCE_PATH);
        return prompt
                .replace(ReadAgentConstants.VAR_TODAY, today())
                .replace(ReadAgentConstants.VAR_READ_TOOL_NAME, readToolName);
    }

    private static String today() {
        return LocalDate.now(ZoneId.of(ReadAgentConstants.TIMEZONE)).toString();
    }

    private static String loadResource(String path) {
        try (InputStream is = SystemPromptBuilder.class.getResourceAsStream(path)) {
            if (is == null) {
                throw new IllegalStateException("Resource not found: " + path);
            }
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to load resource: " + path, e);
        }
    }
}

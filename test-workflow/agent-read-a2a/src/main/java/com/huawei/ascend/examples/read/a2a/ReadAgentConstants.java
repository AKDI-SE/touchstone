/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

/**
 * Constants for the read-agent A2A agent (Deep Research 网页阅读子智能体).
 *
 * <p>Naming mirrors {@code TripAgentConstants} in agent-trip-a2a.
 */
public final class ReadAgentConstants {

    /** OpenJiuwen / A2A agent identifier (must match travel-ascend remote-agents target). */
    public static final String AGENT_ID = "read-agent";

    /** System prompt resource path. */
    public static final String PROMPT_RESOURCE_PATH = "/prompts/read-agent-system-prompt.md";

    /** Template variable: today's date (yyyy-MM-dd, Asia/Shanghai). */
    public static final String VAR_TODAY = "{today}";

    /** Template variable: runtime-injected read tool name. */
    public static final String VAR_READ_TOOL_NAME = "{read_tool_name}";

    /** Default ReAct max iterations. */
    public static final int DEFAULT_MAX_ITERATIONS = 5;

    /** Timezone for "today" injection in system prompt. */
    public static final String TIMEZONE = "Asia/Shanghai";

    /**
     * The read tool name exposed to the agent — equals the {@code read_url} tool id.
     */
    public static String readToolName() {
        return "read_url";
    }

    private ReadAgentConstants() {
    }
}

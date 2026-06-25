/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
 */

package com.huawei.ascend.examples.read.a2a;

import com.huawei.ascend.runtime.engine.AgentExecutionContext;
import com.huawei.ascend.runtime.engine.openjiuwen.OpenJiuwenAgentRuntimeHandler;
import com.huawei.ascend.runtime.engine.openjiuwen.OpenJiuwenCheckpointerConfigurer;
import com.openjiuwen.core.foundation.tool.Tool;
import com.openjiuwen.core.runner.Runner;
import com.openjiuwen.core.runner.base.TagMatchStrategy;
import com.openjiuwen.core.session.checkpointer.Checkpointer;
import com.openjiuwen.core.singleagent.BaseAgent;
import com.openjiuwen.core.singleagent.ReActAgent;
import com.openjiuwen.core.singleagent.agents.ReActAgentConfig;
import com.openjiuwen.core.singleagent.schema.AgentCard;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.a2aproject.sdk.spec.AgentCapabilities;
import org.a2aproject.sdk.spec.AgentInterface;
import org.a2aproject.sdk.spec.AgentProvider;
import org.a2aproject.sdk.spec.AgentSkill;
import org.a2aproject.sdk.spec.TransportProtocol;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring wiring for the read-agent A2A module. Mirrors the layout of
 * {@code TripAgentConfiguration} in agent-trip-a2a.
 *
 * <p>Profile switching (design doc §4.5):
 * <ul>
 *   <li>{@code read-agent.backend=stub} (default in stub profile) → {@link StubDocumentReader}.</li>
 *   <li>{@code read-agent.backend=prod} → {@link HtmlDocumentReader} (real HTTP).</li>
 * </ul>
 */
@Configuration(proxyBeanMethods = false)
public class ReadAgentConfiguration {

    @Bean
    Checkpointer readCheckpointer() {
        return OpenJiuwenCheckpointerConfigurer.setInMemoryDefault();
    }

    /** Stub backend — no network, serves fixtures from classpath. */
    @Bean
    @ConditionalOnProperty(name = "read-agent.backend", havingValue = "stub")
    DocumentReader stubDocumentReader() {
        return new StubDocumentReader();
    }

    /** Prod backend — real HTTP via JDK HttpClient + jsoup/readability4j. */
    @Bean
    @ConditionalOnProperty(name = "read-agent.backend", havingValue = "prod", matchIfMissing = true)
    DocumentReader htmlDocumentReader() {
        return new HtmlDocumentReader();
    }

    @Bean
    OpenJiuwenAgentRuntimeHandler readAgentHandler(
            DocumentReader documentReader,
            @Value("${read-agent.llm.model-provider}") String modelProvider,
            @Value("${read-agent.llm.api-key}") String apiKey,
            @Value("${read-agent.llm.api-base}") String apiBase,
            @Value("${read-agent.llm.model-name}") String modelName,
            @Value("${read-agent.llm.ssl-verify}") boolean sslVerify,
            @Value("${read-agent.llm.max-iterations:"
                    + ReadAgentConstants.DEFAULT_MAX_ITERATIONS + "}") int maxIterations) {
        return new ReadAgentHandler(
                modelProvider, apiKey, apiBase, modelName, sslVerify, maxIterations, documentReader);
    }

    @Bean
    org.a2aproject.sdk.spec.AgentCard readAgentCard() {
        return org.a2aproject.sdk.spec.AgentCard.builder()
                .name(ReadAgentConstants.AGENT_ID)
                .description("Deep-research web page reading sub-agent. Given a public-web URL "
                        + "(and optional focus question), fetches the HTML, extracts the main "
                        + "content with jsoup + readability4j, detects SPA-rendered and "
                        + "access-restricted pages, and returns a structured summary with "
                        + "metadata (title, sections, author, publish_date, doc_type).")
                .version("0.1.0")
                .provider(new AgentProvider("spring-ai-ascend", ""))
                .capabilities(AgentCapabilities.builder()
                        .streaming(true)
                        .pushNotifications(false)
                        .extendedAgentCard(false)
                        .build())
                .defaultInputModes(List.of("text"))
                .defaultOutputModes(List.of("text", "artifact"))
                .skills(List.of(
                        AgentSkill.builder()
                                .id("read_url")
                                .name("Read a public web page")
                                .description("Fetch a public-web URL and extract its main content. "
                                        + "Pass the URL (and optional focus_question). Returns the "
                                        + "title, content_markdown, sections, a ≤200-字 summary, "
                                        + "and metadata including doc_type "
                                        + "(pricing_page|blog|news|doc|spa_blocked|cloudflare_403|other). "
                                        + "When doc_type is spa_blocked/cloudflare_403/other the "
                                        + "content fields are empty so the caller can switch source.")
                                .tags(List.of("read", "fetch", "html", "deep-research"))
                                .examples(List.of(
                                        "帮我抓取 https://www.volcengine.com/docs/240/pricing 并关注豆包 Pro 4K 的输入价格",
                                        "Read https://bailian.console.aliyun.com/pricing and extract Qwen pricing"))
                                .inputModes(List.of("text"))
                                .outputModes(List.of("text"))
                                .build()))
                .supportedInterfaces(List.of(
                        new AgentInterface(TransportProtocol.JSONRPC.asString(), "/a2a")))
                .build();
    }

    /**
     * Runtime handler that builds a fresh ReAct agent per invocation, registers the
     * {@code read_url} tool against the global Runner, and installs the system prompt
     * via {@code addPromptBuilderSection} so runtime rails (memory/trajectory) co-exist.
     *
     * <p>Mirrors {@code TripAgentHandler} in agent-trip-a2a.
     */
    static final class ReadAgentHandler extends OpenJiuwenAgentRuntimeHandler {

        private static final String AGENT_ID_PREFIX = "read-agent-";
        private static final AtomicLong INSTANCE_COUNTER = new AtomicLong();

        private final String modelProvider;
        private final String apiKey;
        private final String apiBase;
        private final String modelName;
        private final boolean sslVerify;
        private final int maxIterations;
        private final DocumentReader documentReader;
        private final Tool readTool;

        ReadAgentHandler(
                String modelProvider,
                String apiKey,
                String apiBase,
                String modelName,
                boolean sslVerify,
                int maxIterations,
                DocumentReader documentReader) {
            super(ReadAgentConstants.AGENT_ID);
            this.modelProvider = modelProvider;
            this.apiKey = apiKey;
            this.apiBase = apiBase;
            this.modelName = modelName;
            this.sslVerify = sslVerify;
            this.maxIterations = maxIterations;
            this.documentReader = documentReader;
            this.readTool = new ReadUrlTool(documentReader);
        }

        @Override
        protected BaseAgent createOpenJiuwenAgent(AgentExecutionContext context) {
            // Per-invocation agent id so multiple read agents in the same process don't
            // fight over the global Runner's tag→tool index.
            String agentId = AGENT_ID_PREFIX + INSTANCE_COUNTER.incrementAndGet();

            AgentCard card = AgentCard.builder()
                    .id(agentId)
                    .name(agentId)
                    .description("Deep Research 网页阅读子智能体（ReAct + jsoup/readability4j）")
                    .build();
            ReActAgent agent = new ReActAgent(card);
            String systemPrompt = SystemPromptBuilder.build(ReadAgentConstants.readToolName());
            ReActAgentConfig config = ReActAgentConfig.builder()
                    .promptTemplate(List.of(Map.of("role", "system", "content", systemPrompt)))
                    .maxIterations(maxIterations)
                    .build()
                    .configureModelClient(modelProvider, apiKey, apiBase, modelName, sslVerify);
            agent.configure(config);

            // Register the read_url tool for this agent instance.
            try {
                Runner.resourceMgr().removeTool(
                        readTool.getCard().getId(), agentId, TagMatchStrategy.ALL, true);
            } catch (RuntimeException ignored) {
                // expected on first registration
            }
            Runner.resourceMgr().addTool(readTool, agentId);
            agent.getAbilityManager().add(readTool.getCard());
            return agent;
        }
    }
}

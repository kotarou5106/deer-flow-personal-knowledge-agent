"use client";

import { useQueryClient } from "@tanstack/react-query";
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";

import { useAuth } from "@/core/auth/AuthProvider";

import { createKnowledgeClient } from "./client";
import {
  resolveKnowledgeFrontendConfig,
  type KnowledgeConfigOverrides,
  type KnowledgeFrontendConfig,
} from "./config";
import { DemoKnowledgeTransport } from "./demo";
import { GatewayKnowledgeTransport } from "./transport";
import type { KnowledgeClient, KnowledgeTransport } from "./types";

type KnowledgeContextValue = {
  config: KnowledgeFrontendConfig;
  client: KnowledgeClient;
  transport: KnowledgeTransport;
};

const KnowledgeContext = createContext<KnowledgeContextValue | undefined>(
  undefined,
);

export function createKnowledgeRuntime(
  overrides?: KnowledgeConfigOverrides,
): KnowledgeContextValue {
  const config = resolveKnowledgeFrontendConfig(overrides);
  const transport = config.demoMode
    ? new DemoKnowledgeTransport()
    : new GatewayKnowledgeTransport(config);
  return {
    config,
    transport,
    client: createKnowledgeClient(transport),
  };
}

export function KnowledgeProvider({
  children,
  configOverrides,
}: Readonly<{
  children: ReactNode;
  configOverrides?: KnowledgeConfigOverrides;
}>) {
  const runtime = useMemo(
    () => createKnowledgeRuntime(configOverrides),
    [configOverrides],
  );
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userKey = user?.id ?? null;
  const previousUserKey = useRef(userKey);

  useEffect(() => {
    if (previousUserKey.current !== userKey) {
      queryClient.removeQueries({ queryKey: ["knowledge"] });
      previousUserKey.current = userKey;
    }
  }, [queryClient, userKey]);

  return (
    <KnowledgeContext.Provider value={runtime}>
      {children}
    </KnowledgeContext.Provider>
  );
}

export function useKnowledgeRuntime(): KnowledgeContextValue {
  const context = useContext(KnowledgeContext);
  if (!context) {
    throw new Error("useKnowledgeRuntime must be used inside KnowledgeProvider.");
  }
  return context;
}

export function useKnowledgeClient(): KnowledgeClient {
  return useKnowledgeRuntime().client;
}

export function useKnowledgeConfig(): KnowledgeFrontendConfig {
  return useKnowledgeRuntime().config;
}

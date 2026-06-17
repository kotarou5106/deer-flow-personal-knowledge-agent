"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { useKnowledgeClient } from "./context";
import { isNonRetryableKnowledgeError } from "./errors";
import type {
  IngestionCreateInput,
  KnowledgeJob,
  KnowledgeJobAccepted,
  KnowledgeRequestOptions,
} from "./types";

export const knowledgeQueryKeys = {
  all: ["knowledge"] as const,
  job: (jobId: string) => ["knowledge", "jobs", jobId] as const,
  activity: () => ["knowledge", "activity"] as const,
  sources: () => ["knowledge", "sources"] as const,
};

export function shouldRetryKnowledgeQuery(
  failureCount: number,
  error: unknown,
): boolean {
  return failureCount < 2 && !isNonRetryableKnowledgeError(error);
}

export function useKnowledgeJob(
  jobId: string | undefined,
  options?: Omit<
    UseQueryOptions<KnowledgeJob>,
    "queryKey" | "queryFn" | "enabled" | "retry"
  >,
) {
  const client = useKnowledgeClient();
  return useQuery({
    queryKey: jobId ? knowledgeQueryKeys.job(jobId) : ["knowledge", "jobs", ""],
    queryFn: ({ signal }) =>
      client.getJob(jobId ?? "", { signal } satisfies KnowledgeRequestOptions),
    enabled: Boolean(jobId),
    retry: shouldRetryKnowledgeQuery,
    ...options,
  });
}

export function useSubmitKnowledgeIngestion(
  options?: UseMutationOptions<
    KnowledgeJobAccepted,
    unknown,
    IngestionCreateInput
  >,
) {
  const client = useKnowledgeClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => client.createIngestion(input),
    retry: false,
    ...options,
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.activity() });
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.sources() });
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.job(data.job_id) });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}

export function useCancelKnowledgeJob(
  options?: UseMutationOptions<KnowledgeJobAccepted, unknown, string>,
) {
  const client = useKnowledgeClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId) => client.cancelJob(jobId),
    retry: false,
    ...options,
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.job(data.job_id) });
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.activity() });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}

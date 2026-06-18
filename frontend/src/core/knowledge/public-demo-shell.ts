import { isStaticWebsiteOnly } from "@/core/static-mode";

import { resolveKnowledgeFrontendConfig } from "./config";
import { knowledgePublicDemoLinks, workspaceProjectIntroLink } from "./public-demo";

export const publicKnowledgeDemoShellLinks = [
  workspaceProjectIntroLink,
  {
    href: knowledgePublicDemoLinks.demo,
    label: "知识工作区",
  },
] as const;

export const hiddenPublicKnowledgeDemoShellLabels = [
  "新对话",
  "演示对话",
  "对话",
  "智能体",
  "渠道",
  "设置和更多",
] as const;

export function isPublicKnowledgeDemoShell() {
  return isStaticWebsiteOnly() || resolveKnowledgeFrontendConfig().demoMode;
}

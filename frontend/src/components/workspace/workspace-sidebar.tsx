"use client";

import { BookOpenIcon, InfoIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  isPublicKnowledgeDemoShell,
  publicKnowledgeDemoShellLinks,
} from "@/core/knowledge/public-demo-shell";

import { WorkspaceChannelsList } from "./channels/workspace-channels-list";
import { RecentChatList } from "./recent-chat-list";
import { WorkspaceHeader } from "./workspace-header";
import { WorkspaceNavChatList } from "./workspace-nav-chat-list";
import { WorkspaceNavMenu } from "./workspace-nav-menu";

export function WorkspaceSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  const { open: isSidebarOpen } = useSidebar();
  if (isPublicKnowledgeDemoShell()) {
    return <PublicKnowledgeDemoSidebar {...props} />;
  }
  return (
    <>
      <Sidebar variant="sidebar" collapsible="icon" {...props}>
        <SidebarHeader className="py-0">
          <WorkspaceHeader />
        </SidebarHeader>
        <SidebarContent>
          <WorkspaceNavChatList />
          <WorkspaceChannelsList />
          {isSidebarOpen && <RecentChatList />}
        </SidebarContent>
        <SidebarFooter>
          <WorkspaceNavMenu />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
    </>
  );
}

function PublicKnowledgeDemoSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();
  return (
    <Sidebar variant="sidebar" collapsible="icon" {...props}>
      <SidebarHeader className="py-0">
        <div className="flex h-12 items-center justify-between gap-2 px-2">
          <Link
            href="/knowledge"
            className="text-primary min-w-0 truncate font-serif text-sm"
          >
            个人知识智能体
          </Link>
          <SidebarTrigger />
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu className="px-2 pt-2">
          {publicKnowledgeDemoShellLinks.map((item) => {
            const Icon = item.href === "/knowledge" ? InfoIcon : BookOpenIcon;
            const isActive =
              item.href === "/knowledge"
                ? pathname === item.href
                : pathname?.startsWith(item.href);
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton isActive={isActive} asChild>
                  <Link className="text-muted-foreground" href={item.href}>
                    <Icon size={16} />
                    <span>{item.label}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}

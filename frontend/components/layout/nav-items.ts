import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  BookOpen,
  ClipboardCheck,
  FileQuestion,
  FolderOpen,
  LayoutDashboard,
  Settings,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    description: "Workspace overview and backend health",
  },
  {
    label: "My Library",
    href: "/library",
    icon: FolderOpen,
    description: "Uploaded PDFs, images, and text sources",
  },
  {
    label: "Smart Notes",
    href: "/notes",
    icon: BookOpen,
    description: "Detailed notes, quick revision, and strategies",
  },
  {
    label: "Question Bank",
    href: "/question-bank",
    icon: FileQuestion,
    description: "Extracted and generated practice questions",
  },
  {
    label: "Tests",
    href: "/tests",
    icon: ClipboardCheck,
    description: "Test builder and timed practice modes",
  },
  {
    label: "Performance",
    href: "/performance",
    icon: BarChart3,
    description: "Cross-attempt accuracy and speed trends",
  },
  {
    label: "Settings",
    href: "/settings",
    icon: Settings,
    description: "Exam preferences and system status",
  },
] as const;

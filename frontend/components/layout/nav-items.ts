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
  caption?: string;
  matchPrefixes?: readonly string[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    description: "Workspace overview and next study steps",
    caption: "Study home & progress",
  },
  {
    label: "My Library",
    href: "/library",
    icon: FolderOpen,
    description: "Uploaded PDFs, images, and text sources",
    caption: "Uploaded PDFs & files",
    matchPrefixes: ["/documents"],
  },
  {
    label: "Smart Notes",
    href: "/notes",
    icon: BookOpen,
    description: "Detailed notes, quick revision, and strategies",
    caption: "PDF → full study notes",
  },
  {
    label: "Question Bank",
    href: "/question-bank",
    icon: FileQuestion,
    description: "Extracted and generated practice questions",
    caption: "PDF → practice MCQs",
  },
  {
    label: "Practice Tests",
    href: "/tests",
    icon: ClipboardCheck,
    description: "Test builder and timed practice modes",
    caption: "PDF / topic → mock test",
    matchPrefixes: ["/attempts"],
  },
  {
    label: "Performance",
    href: "/performance",
    icon: BarChart3,
    description: "Cross-attempt accuracy and speed trends",
    caption: "Weak topics & trends",
  },
  {
    label: "Settings",
    href: "/settings",
    icon: Settings,
    description: "Account, exam preferences, and system health",
    caption: "Account & system status",
  },
] as const;

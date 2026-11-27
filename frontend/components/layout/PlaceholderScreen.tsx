import { Clock } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface PlaceholderScreenProps {
  title: string;
  description: string;
  milestone: string;
  capabilities: readonly string[];
}

export function PlaceholderScreen({
  title,
  description,
  milestone,
  capabilities,
}: PlaceholderScreenProps) {
  return (
    <div>
      <PageHeader
        title={title}
        description={description}
        actions={<Badge variant="outline">{milestone}</Badge>}
      />
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <CardTitle>Module Scheduled for {milestone}</CardTitle>
          </div>
          <CardDescription>
            This navigation route is wired in the M0 foundation shell. No sample
            or placeholder study data is displayed until backend endpoints for
            this milestone are connected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            {capabilities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

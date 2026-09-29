import type { Metadata } from "next";

import { ReportForm, type ReportTarget } from "@/components/ReportForm";
import { getStrings } from "@/lib/i18n.server";

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: strings.reportHeading };
}

type Params = Partial<Record<keyof ReportTarget, string | string[]>>;

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

export default async function ReportPage({ searchParams }: { searchParams: Promise<Params> }) {
  const found = await searchParams;
  return (
    <ReportForm
      target={{
        document: one(found.document),
        segment: one(found.segment),
        quiz: one(found.quiz),
        question: one(found.question),
        kind: one(found.kind),
      }}
    />
  );
}

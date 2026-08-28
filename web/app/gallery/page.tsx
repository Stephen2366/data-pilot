import { ResultView } from "@/components/result-view";
import { agentResponseSchema } from "@/lib/contracts";
import Link from "next/link";
import { notFound } from "next/navigation";
import sqlComplete from "@/test/fixtures/sql-complete.json";
import hybridPartial from "@/test/fixtures/hybrid-partial.json";
import blocked from "@/test/fixtures/blocked.json";
import externalUnavailable from "@/test/fixtures/external-unavailable.json";
import legacyClarification from "@/test/fixtures/legacy-clarification.json";

const states = [
  ["SQL · complete", sqlComplete],
  ["Hybrid · partial", hybridPartial],
  ["Safety · blocked", blocked],
  ["Runtime · external unavailable", externalUnavailable],
  ["Legacy · clarification", legacyClarification],
] as const;

/** 开发态视觉回归 gallery；fixture 明示标签，绝不作为真实演示结果。 */
export default function GalleryPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main className="gallery-shell">
      <header>
        <p className="eyebrow">DEVELOPMENT FIXTURE GALLERY</p>
        <h1>DataPilot 产品状态画廊</h1>
        <p>以下全部是 Python-authoritative contract fixture，只用于视觉与自动化验证。</p>
        <Link href="/">返回真实工作台</Link>
      </header>
      <div className="gallery-grid">
        {states.map(([label, fixture]) => (
          <section key={label}>
            <h2>{label}</h2>
            <ResultView response={agentResponseSchema.parse(fixture)} />
          </section>
        ))}
      </div>
    </main>
  );
}

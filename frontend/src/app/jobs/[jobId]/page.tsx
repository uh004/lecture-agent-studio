import { AppHeader } from "@/components/app-header";
import { JobScreen } from "@/components/job-screen";

type JobPageProps = {
  params: Promise<{ jobId: string }>;
};

export default async function JobPage({ params }: JobPageProps) {
  const { jobId } = await params;

  return (
    <div className="site-shell">
      <AppHeader />
      <main className="page-container job-page">
        <JobScreen jobId={jobId} />
      </main>
    </div>
  );
}

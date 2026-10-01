import { BrandLoading } from '../../ui/BrandLoading';
import { useQuery } from '@tanstack/react-query';
import { FrontierKnowledgeLinks } from './FrontierKnowledgeLinks';
import { FrontierReadingPriority } from './FrontierReadingPriority';
import { readRecordInsights } from './readingInsightsApi';

export interface FrontierRecordInsightsProps { recordId: string; asOf?: string }
export function FrontierRecordInsights({ recordId, asOf }: FrontierRecordInsightsProps) {
  const query = useQuery({ queryKey: ['frontier-record-insights', recordId, asOf],
    queryFn: () => readRecordInsights(recordId, asOf), enabled: Boolean(recordId),
    staleTime: 0, refetchOnMount: 'always', refetchInterval: false, refetchOnWindowFocus: false, refetchOnReconnect: false, retry: false,
  });
  if (query.isPending || query.isFetching) return <BrandLoading compact message="正在读取阅读依据…" />;
  if (query.isError || !query.data) return <div role="alert">阅读依据暂时无法读取。<button onClick={() => void query.refetch()}>重试</button></div>;
  const { priority, links } = query.data;
  if (priority.recordId !== recordId || links.recordId !== recordId ||
      priority.recordVersion !== links.recordVersion || priority.snapshotHash !== links.snapshotHash)
    return <div role="alert">文献版本已变化。<button onClick={() => void query.refetch()}>刷新阅读依据</button></div>;
  return <><button onClick={() => void query.refetch()}>刷新阅读依据</button><FrontierReadingPriority priority={priority}/><FrontierKnowledgeLinks links={links}/></>;
}

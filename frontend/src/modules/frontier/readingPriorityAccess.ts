import { readReadingPriorities as load } from './readingInsightsApi';

export function readReadingPriorities(options?: Parameters<typeof load>[0]) {
  return load(options);
}

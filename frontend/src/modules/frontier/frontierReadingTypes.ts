import type { readFrontierCalendar, readFrontierPeriod } from './frontierApi';

// Derive the reading UI inputs from the module adapter, keeping transport-code
// imports confined to the approved API boundary.
export type FrontierCalendarData = Awaited<ReturnType<typeof readFrontierCalendar>>;
export type FrontierPeriodData = Awaited<ReturnType<typeof readFrontierPeriod>>;

export type Company = {
  slug: string;
  name: string;
  group: 'newer' | 'established';
  description: string;
};

export const companyGroups = {
  newer: {
    heading: 'Newer and specialist tools',
    description:
      'Smaller or more recently founded products, several built specifically for electrical or trades work.',
  },
  established: {
    heading: 'Established platforms',
    description:
      'Larger, more widely adopted field service platforms with longer track records.',
  },
} as const;

export const companies: Company[] = [
  {
    slug: 'elyos-ai',
    name: 'Elyos AI',
    group: 'newer',
    description: 'AI assistants built for skilled trades.',
  },
  {
    slug: 'acewatt',
    name: 'AceWatt',
    group: 'newer',
    description: 'Built for electrical contractors from day one.',
  },
  {
    slug: 'quoteiq',
    name: 'QuoteIQ',
    group: 'newer',
    description: 'AI estimating, dispatch, invoicing, and a 24/7 AI call team.',
  },
  {
    slug: 'serviceagent',
    name: 'ServiceAgent',
    group: 'newer',
    description: 'AI voice agents that capture missed calls.',
  },
  {
    slug: 'tradefix',
    name: 'TradeFix',
    group: 'newer',
    description: 'A modern alternative aimed at small HVAC, plumbing, and electrical shops.',
  },
  {
    slug: 'fieldpulse',
    name: 'FieldPulse',
    group: 'newer',
    description: 'A mid-size field service challenger for the trades.',
  },
  {
    slug: 'servicetitan',
    name: 'ServiceTitan',
    group: 'established',
    description: 'The large enterprise field service platform.',
  },
  {
    slug: 'housecall-pro',
    name: 'Housecall Pro',
    group: 'established',
    description: 'A popular pick for small and solo operators.',
  },
  {
    slug: 'jobber',
    name: 'Jobber',
    group: 'established',
    description: 'A popular pick for small and solo operators.',
  },
  {
    slug: 'fieldedge',
    name: 'FieldEdge',
    group: 'established',
    description: 'A mid-market field service platform.',
  },
];

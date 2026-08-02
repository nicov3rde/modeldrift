export type QuestionGroup = {
  heading: string;
  intro: string;
  questions: string[];
};

export const questionGroups: QuestionGroup[] = [
  {
    heading: 'Problem-aware: the buyer hasn’t named the category yet',
    intro: 'Questions a contractor might ask before they know software like this exists.',
    questions: [
      'How do I stop losing track of jobs and invoices in my electrical business',
      'How can a small electrical contractor schedule jobs and dispatch techs',
      'How do electricians write estimates faster',
      'What’s the best way to handle missed customer calls as an electrician',
    ],
  },
  {
    heading: 'Category-aware: actively evaluating',
    intro: 'Questions from someone who knows a software category exists and is comparing options.',
    questions: [
      'Best software for electrical contractors',
      'Best field service software for a small electrical shop',
      'What software do electricians use to run their business',
      'Best electrical contractor software for a 5-person shop',
      'Best software for a solo electrician',
      'Best electrical estimating software',
    ],
  },
  {
    heading: 'Capability-specific: questions that describe a real product’s exact strengths',
    intro: 'Questions phrased around specific features, testing whether engines surface the products built for them.',
    questions: [
      'AI estimating software for electricians',
      'Software built specifically for electrical contractors',
      'AI phone answering service for electrical contractors',
      'Electrical contractor software with load calculations and panel schedules',
      'Software for electrical contractors that handles permits and code compliance',
    ],
  },
  {
    heading: 'Comparison and decision',
    intro: 'Questions asked late in the buying process, often naming an incumbent directly.',
    questions: [
      'ServiceTitan alternatives',
      'Cheaper alternative to ServiceTitan for electricians',
      'Jobber vs Housecall Pro for electrical work',
      'Is ServiceTitan worth it for a small electrical contractor',
      'How much does electrical contractor software cost',
    ],
  },
];

export const totalQuestionCount = questionGroups.reduce(
  (sum, group) => sum + group.questions.length,
  0
);

export const brandDirectQuestions = [
  'What is [company]',
  'Is [company] good for electrical contractors',
];

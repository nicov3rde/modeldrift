import raw from '../../data/question-set.v1.json';

export type QuestionGroup = {
  id: string;
  heading: string;
  intro: string;
  questions: { id: string; text: string; note?: string }[];
};

export const freezeDate = raw.freeze_date;

export const questionGroups: QuestionGroup[] = raw.buckets.map((bucket) => ({
  id: bucket.id,
  heading: `${bucket.heading}: ${bucket.subheading}`,
  intro: bucket.note ?? '',
  questions: bucket.questions.map((q) => ({ id: q.id, text: q.text, note: 'note' in q ? q.note : undefined })),
}));

export const totalQuestionCount = questionGroups.reduce(
  (sum, group) => sum + group.questions.length,
  0
);

export const segmentSkewNote = raw.segment_skew_note;

export const repetitions = raw.repetitions;

export const brandDirectQuestions = raw.brand_direct.templates.map((t) => t.text.replace('{company}', '[company]'));

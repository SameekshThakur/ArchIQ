import { describe, expect, it } from 'vitest';
import { fmtMoneyK, fmtNum, titleCase } from '@/lib/format';

describe('format helpers', () => {
  it('formats money in thousands and millions', () => {
    expect(fmtMoneyK(490)).toBe('$490k');
    expect(fmtMoneyK(1439)).toBe('$1.4M');
  });
  it('groups digits', () => expect(fmtNum(1234567)).toBe('1,234,567'));
  it('title-cases snake and kebab identifiers', () => {
    expect(titleCase('ticket_raised')).toBe('Ticket Raised');
    expect(titleCase('no-go')).toBe('No Go');
  });
});

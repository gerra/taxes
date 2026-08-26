import { gbp, lastElapsedTaxYear, num, shortDate } from '../utils/format'

test('gbp formats decimals and handles nulls', () => {
  expect(gbp('1234.5')).toBe('£1,234.50')
  expect(gbp(0)).toBe('£0.00')
  expect(gbp(null)).toBe('—')
  expect(gbp('nonsense')).toBe('—')
})

test('num trims trailing zeros', () => {
  expect(num('50.000000', 4)).toBe('50')
  expect(num('0.1250', 4)).toBe('0.125')
})

test('shortDate renders UK style', () => {
  expect(shortDate('2025-04-05')).toBe('5 Apr 2025')
})

test('lastElapsedTaxYear flips on 6 April', () => {
  expect(lastElapsedTaxYear(new Date('2026-08-26'))).toBe(2025)
  expect(lastElapsedTaxYear(new Date('2026-04-05'))).toBe(2024)
  expect(lastElapsedTaxYear(new Date('2026-04-06'))).toBe(2025)
})

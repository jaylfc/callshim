# roman

Implement `src/roman.js`:

- `toRoman(n)`: integer 1..3999 to a Roman numeral using subtractive notation (4 = "IV", 9 = "IX", 40 = "XL", 90 = "XC", 400 = "CD", 900 = "CM"). Throw a `RangeError` for anything else, including non-integers.
- `fromRoman(s)`: the reverse, for canonical numerals only (the exact form `toRoman` produces, uppercase). Throw a `SyntaxError` for anything else, such as "IIII", "VX", "IC", "", or lowercase.

`node --test` runs the tests in test/. Commit with git when they pass.

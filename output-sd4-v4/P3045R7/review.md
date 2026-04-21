# [P3045R7](https://github.com/cppalliance/paperlint/blob/feature/sd4-rubric-v2/output-sd4-v4/P3045R7/paper.md) - Quantities and units library
Answered 1 of 1 applicable questions.

**Q1. Does the paper show code of the feature it is proposing?**
> ```
> import std;
> 
> using namespace std::si::unit_symbols;
> 
> // simple numeric operations
> static_assert(10 * km / 2 == 5 * km);
> 
> // conversions to common units
> static_assert(1 * h == 3600 * s);
> static_assert(1 * km + 1 * m == 1001 * m);
> 
> // derived quantities
> static_assert(1 * km / (1 * s) == 1000 * m / s);
> static_assert(2 * km / h * (2 * h) == 4 * km);
> static_assert(2 * km / (2 * km / h) == 1 * h);
> 
> static_assert(2 * m * (3 * m) == 6 * m2);
> 
> static_assert(10 * km / (5 * km) == 2);
> 
> static_assert(1000 / (1 * s) == 1 * kHz);
> ```

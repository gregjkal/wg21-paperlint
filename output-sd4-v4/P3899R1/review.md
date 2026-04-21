# [P3899R1](https://github.com/cppalliance/paperlint/blob/feature/sd4-rubric-v2/output-sd4-v4/P3899R1/paper.md) - Clarify the behavior of floating-point overflow
Answered 1 of 1 applicable questions.

**Q1. Does the paper show code of the feature it is proposing?**
> constexpr std::float32_t min = std::numeric_limits<std::float32_t>::min(); // OK
> constexpr std::float32_t max = std::numeric_limits<std::float32_t>::max(); // OK
> constexpr std::float32_t inf = std::numeric_limits<std::float32_t>::infinity(); // OK
> constexpr std::float32_t nan = std::numeric_limits<std::float32_t>::quiet_NaN(); // OK
> 
> constexpr std::float32_t inf2 = inf * 2; // OK, also positive infinity
> constexpr std::float32_t zero = min / max; // OK, result cannot be represented, and is rounded to zero
> constexpr std::float32_t oflo = max * 2; // error: defined, but not a constant expression ([expr.const])
> constexpr std::float32_t nan2 = nan * 2; // OK: propagating a NaN
> constexpr std::float32_t udef = inf * 0; // error: result is not mathematically defined
> constexpr std::float32_t div0 = max / 0; // error: division by zero is undefined ([expr.mul])

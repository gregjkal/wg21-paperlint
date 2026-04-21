# [P3971R0](https://github.com/cppalliance/paperlint/blob/feature/sd4-rubric-v2/output-sd4-v4/P3971R0/paper.md) - std::rebind - Generalized Type Rebinding for Containers and Uniform-Element Types
Answered 1 of 1 applicable questions.

**Q1. Does the paper show code of the feature it is proposing?**
> // Arrays - preserves size
> std::array<float, 4> af = {1.0f, 2.0f, 3.0f, 4.0f};
> std::array<double, 4> ad = std::rebind<double>(af);
> 
> // Type computation
> using ArrayDouble4 = std::rebind_t<double, decltype(af)>;
> static_assert(std::is_same_v<ArrayDouble4, std::array<double, 4>>);
> 
> // Vectors - preserves allocator
> std::vector<int> vi = {1, 2, 3, 4, 5};
> std::vector<long> vl = std::rebind<long>(vi);
> 
> // Complex numbers
> std::complex<float> cf{3.0f, 4.0f};
> std::complex<double> cd = std::rebind<double>(cf);

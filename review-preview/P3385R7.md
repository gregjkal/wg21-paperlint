# [P3385R7](https://github.com/cppalliance/paperlint/blob/feature/sd4-rubric-v2/output-sd4-v4/P3385R7/paper.md) - Attributes reflection
Answered 1 of 1 applicable questions.

**Q1. Does the paper show code of the feature it is proposing?**
> template<class T>
> struct MigratedT {
>  struct impl;
>  consteval {
>  std::vector<std::meta::info> migratedMembers = {};
>  for (auto member : nonstatic_data_members_of(^^T, ctx)) {
>  if (!std::meta::has_attribute(member, ^^[[deprecated]])) {
>  migratedMembers.push_back(data_member_spec(
>  std::meta::type_of(member),
>  {.name = std::meta::identifier_of(member)}
>  ));
>  }
>  }
>  define_aggregate(^^impl, migratedMembers);
>  }
> };

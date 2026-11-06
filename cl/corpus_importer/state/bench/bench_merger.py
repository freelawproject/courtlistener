from typing import ClassVar

from pytest_benchmark.fixture import BenchmarkFixture

from cl.corpus_importer.state.merger import Attribute, Merger
from cl.lasc.models import Docket


class AttributeSpecificationBench:
    def bench_subclass_init_bare(self, benchmark: BenchmarkFixture):
        def run():
            class BareMerger(Merger[None, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

        benchmark(run)

    def bench_init_bare(self, benchmark: BenchmarkFixture):
        class BareMerger(Merger[None, None, Docket]):
            model: ClassVar[type[Docket]] = Docket

        benchmark(BareMerger, None, params=None)

    def bench_subclass_init_attr(self, benchmark: BenchmarkFixture):
        def run():
            class AttrMerger(Merger[None, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

                docket_number: str = Attribute(default="abcdefg")

        benchmark(run)

    def bench_init_attr(self, benchmark: BenchmarkFixture):
        class AttrMerger(Merger[None, None, Docket]):
            model: ClassVar[type[Docket]] = Docket

            docket_number: str = Attribute(default="abcdefg")

        benchmark(AttrMerger, None, params=None)

    def bench_attr_transform(self, benchmark: BenchmarkFixture):
        spec = Attribute(
            transform=lambda scrape, params: None, default="abcdefg"
        )

        benchmark(spec.transform, None, None)

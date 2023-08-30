RPMBUILD = rpmbuild --define "_topdir %(pwd)/build" \
        --define "_builddir %{_topdir}" \
        --define "_rpmdir %{_topdir}" \
        --define "_srcrpmdir %{_topdir}" \
        --define "_sourcedir %(pwd)"

all:
	mkdir -p build
	date --utc +%Y%m%d%H%M%S > VERSION
	${RPMBUILD} --define "_version %(cat VERSION)" -ba rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build/*
	${RPMBUILD} --define "_version %(cat VERSION)" -ba python3-rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build/*
	${RPMBUILD} --define "_version %(cat VERSION)" --define "_telescope clasp" --define "_label CLASP" -ba python3-rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build/*
	${RPMBUILD} --define "_version %(cat VERSION)" --define "_telescope halfmetre" --define "_label Half metre" -ba python3-rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build/*
	${RPMBUILD} --define "_version %(cat VERSION)" --define "_telescope onemetre" --define "_label W1m" -ba python3-rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build/*
	${RPMBUILD} --define "_version %(cat VERSION)" --define "_telescope superwasp" --define "_label SuperWASP" -ba python3-rockit-operations.spec
	mv build/noarch/*.rpm .
	rm -rf build VERSION

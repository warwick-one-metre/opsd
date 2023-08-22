Name:           python3-warwick-clasp-operations
Version:        20230721
Release:        0
License:        GPL3
Summary:        CLASP specific operations code
Url:            https://github.com/warwick-one-metre/opsd
BuildArch:      noarch
Requires:       python3-warwick-observatory-operations python3-astropy python3-rockit-lmount
Requires:       python3-rockit-focuser python3-warwick-observatory-qhy-camera python3-warwick-observatory-raptor-camera python3-rockit-pipeline

%description

%prep

rsync -av --exclude=build .. .

%build
%{__python3} setup_clasp.py build

%install
%{__python3} setup_clasp.py install --prefix=%{_prefix} --root=%{buildroot}
mkdir -p %{buildroot}%{_sysconfdir}/opsd
%{__install} %{_sourcedir}/clasp.json %{buildroot}%{_sysconfdir}/opsd

%files
%defattr(-,root,root,-)
%{python3_sitelib}/*
%defattr(0644,root,root,-)
%{_sysconfdir}/opsd/clasp.json

%changelog

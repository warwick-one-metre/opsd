Name:           python36-warwick-observatory-operations
Version:        2.3.0
Release:        0
License:        GPL3
Summary:        Common backend code for the RASA prototype telescope operations daemon
Url:            https://github.com/warwick-one-metre/
BuildArch:      noarch
Requires:       python36-jsonschema

%description
Part of the observatory software for the W1m and RASA prototype telescopes.

python36-warwick-observatory-operations holds the common operations code.

%prep

rsync -av --exclude=build .. .

%build
%{__python3_other} setup_observatory.py build

%install
%{__python3_other} setup_observatory.py install --prefix=%{_prefix} --root=%{buildroot}

%files
%defattr(-,root,root,-)
%{python3_other_sitelib}/*

%changelog
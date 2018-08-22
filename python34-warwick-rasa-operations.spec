#
# spec file for package python3-warwick-rasa-operations
#
# Copyright (c) 2016 SUSE LINUX Products GmbH, Nuernberg, Germany.
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

Name:           python34-warwick-rasa-operations
Version:        2.1.0
Release:        0
License:        GPL3
Summary:        RASA prototype specific operations code
Url:            https://github.com/warwick-one-metre/
BuildArch:      noarch
Requires:       python34-warwick-rasa-operations

%description
Part of the observatory software for the RASA prototype telescope.

python3-warwick-rasa-operations holds the RASA-specific operations code.

%prep

rsync -av --exclude=build .. .

%build
python3 setup_rasa.py build

%install
python3 setup_rasa.py install --prefix=%{_prefix} --root=%{buildroot}

%files
%defattr(-,root,root,-)
%{python3_sitelib}/*

%changelog
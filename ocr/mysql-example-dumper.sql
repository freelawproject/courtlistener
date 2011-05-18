select documentPlainText from Document where court_id = 'ca1' and dateFiled >= '2010-03-29' and dateFiled <= '2011-03-28' into outfile '/tmp/ca1.words';

import codecs
import copy
import encodings
import functools
import itertools
import tokenize
import traceback


tokens_to_ignore = {tokenize.NEWLINE, tokenize.NL}
insertable_spaces = {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT}
bracket_reverse = {')': '(', ']': '[', '}': '{'}
dummy = tokenize.TokenInfo(60, "", (0, 0), (0, 0), "")


class TokenParser:
    def __init__(self, lines):
        self.idx = 0
        if isinstance(lines[0], str):
            self.iterator = [*tokenize.generate_tokens(
                iter(x for x in lines if x).__next__
            )]
        else:
            self.iterator = lines + [dummy]
        self.length = len(self.iterator)
    def __iter__(self):
        return self
    def __next__(self):
        try:
            val = self.iterator[self.idx]
            self.idx += 1
            return val
        except IndexError as e:
            raise StopIteration(*e.args)
    def __len__(self):
        return len(self.iterator)
    # grammar parsing
    def rep(self, func, minm=0):
        pos = self.idx
        res = []
        while a := func():
            res.append(a)
        if len(res) >= minm:
            return res
        self.idx = pos
    def params(self):
        if a := self.parameters():
            a = (a[0] + [*a[1]], a[1], a[2] + [*a[3]], a[3], a[4],
                 a[5] + [*a[6]], a[6], a[7])
        return a
    def parameters(self):
        if a := self.slash_no_default():
            b = self.rep(self.param_no_default)
            c = dict(self.rep(self.param_with_default))
            res = (a, {}, b, c)
        elif a := self.slash_with_default():
            b = dict(self.rep(self.param_with_default))
            res = a + ([], b)
        elif a := self.rep(self.param_no_default, 1):
            b = dict(self.rep(self.param_with_default))
            res = ([], {}, a, b)
        elif a := self.rep(self.param_with_default, 1):
            a = dict(a)
            res = ([], {}, [], a)
        else:
            if a := self.star_etc():
                return ([], {}, [], {}) + a
            return None
        a = self.star_etc() or (None, [], {}, None)
        return res + a
    def _check_arg(self):
        is_rpar = 0
        if ((tok_str := next(self).string) == ','
                or (is_rpar := tok_str == ')')):
            self.idx -= is_rpar
            return True
        return False
    def slash_no_default(self):
        pos = self.idx
        if ((a := self.rep(self.param_no_default, 1))
                and next(self).string == '/' and self._check_arg()):
            return a
        self.idx = pos
    def slash_with_default(self):
        pos = self.idx
        a = self.rep(self.param_no_default)
        if ((b := self.rep(self.param_with_default, 1))
                and next(self).string == '/' and self._check_arg()):
            return (a, b)
        self.idx = pos
    def star_etc(self):
        pos = self.idx
        if (tok_str := next(self).string) == '*':
            if a := self.param_no_default():
                b = self.rep(self.param_maybe_default)
                b_l, b_d = [], {}
                for x in b:
                    if isinstance(x, tuple):
                        b_d[x[0]] = x[1]
                    else:
                        b_l.append(x)
                return (a, b_l, b_d, self.param_no_default())
            elif (next(self).string == ','
                    and (b := self.rep(self.param_maybe_default, 1))):
                b_l, b_d = [], {}
                for x in b:
                    if isinstance(x, tuple):
                        b_d[x[0]] = x[1]
                    else:
                        b_l.append(x)
                return (None, b_l, b_d, self.param_no_default())
        elif tok_str == '**':
            if a := self.param_no_default():
                return (None, [], {}, a)
        self.idx = pos
    def param_no_default(self):
        pos = self.idx
        if (a := self.param()) and self._check_arg():
            return a
        self.idx = pos
    def param_with_default(self):
        pos = self.idx
        if ((a := self.param()) and (b := self.default())
                and self._check_arg()):
            return (a, b)
        self.idx = pos
    def param_maybe_default(self):
        pos = self.idx
        if a := self.param():
            c = self.default()
            if self._check_arg():
                return (a, c) if c else a
        self.idx = pos
    def param(self):
        if (tok := next(self)).type is tokenize.NAME:
            return tok.string
        self.idx -= 1
    def default(self):
        pos = self.idx
        if (tok := next(self)).string != '=':
            _warn(tok)
            self.idx -= 1
            raise Exception
        tokens, last_br = self.expression(tok)
        if last_br and last_br.string != ')':
            print(f"(error) final bracket is not a parenthesis: {last_br!r}")
            self.idx = pos
            raise Exception
        return tokens
    def expression(self, orig_=None):
        tokens = []
        brackets = []
        if orig_ is None:
            orig_ = self.iterator[self.idx + 1]
        while brackets or (tok := next(self)).string != ',':
            if tok.string == '`':
                orig = tok
                try:
                    while (tok := next(self)).string != '`':
                        tokens.append(tok if tok.string != '\\' else next(self))
                except StopIteration:
                    print("(error) end of file encountered while parsing \n"
                          f"backtick expression: {orig!r}")
                    self.idx = pos
                    raise
            elif tok.string in {'(', '[', '{'}:
                balance.append(tok.string)
            elif b := bracket_reverse.get(tok.string):
                if not brackets:
                    break
                brackets.remove(b)
            elif tok.string is not tokenize.ENDMARKER:
                tokens.append(tok)
            else:
                print("(error) end of file encountered while parsing \n"
                      f"expression: {orig_!r}")
                self.idx = pos
                raise Exception
        else:
            self.idx -= 1
            return tokens, None
        self.idx -= 1
        return tokens, tok
    def args(self):
        pos = self.idx
        pargs = []
        while (a := self.expression())[0]:
            pargs.append(a[0])
            if a[1]:
                break
        if not pargs:
            return
        if not self._check_arg():
            print("(error) end of arg sequence does not end properly; "
                  f"last arg: {pargs[-1][-1]}")
            raise Exception
        kwargs = {}
        while True:
            x = pargs[-1]
            if len(x) > 2 and (n := x[0]).type is tokenize.NAME and x[1].string == '=':
                pargs.pop()
                if n.string not in kwargs:
                    kwargs[n.string] = x[2:]
                else:
                    _warn(n, "(warning) duplicate kwarg ignored: {!r}")
                    continue
            else:
                break
        return pargs, kwargs


def _warn(token=None, message="(warning) unexpected token: {!r}",
          exctype=SyntaxWarning):
    try:
        raise exctype(message.format(token))
    except BaseException as exc:
        traceback.print_exception(exc, exc, exc.__traceback__.tb_next)


def _transfer(dict0, dict1, seq, i=0, stop=None, del_sdict_item=False):
    if stop is None:
        stop = len(seq)
    if del_sdict_item is False:
        while i < stop:
            if (elem := seq[i]) in dict1:
                dict0[elem] = dict1[elem]
                stop -= 1
                del seq[i]
            else:
                i += 1
    else:
        while i < stop:
            if (elem := seq[i]) in dict1:
                dict0[elem] = dict1[elem]
                del dict1[elem]
                stop -= 1
                del seq[i]
            else:
                i += 1
    return stop

def add_offset(body, a0, a1, copy=True, start=0):
    if copy:
        body = body[:]
    c = body[start].start[0]
    if start:
        it = itertools.islice(body, start, None)
    else:
        it = body
    for i, tok in enumerate(it, start=start):
        s0, s1 = tok.start
        e0, e1 = tok.end
        if a1:
            if s0 == c:
                start = (s0+a0, s1+a1)
                if e0 == c:
                    end = (e0+a0, e1+a1)
                else:
                    a1 = 0
                    end = (e0+a0, e1)
            else:
                a1 = 0
                start = (s0+a0, s1)
                end = (e0+a0, e1)
        else:
            start = (s0+a0, s1)
            end = (e0+a0, e1)
        body[i] = tok._replace(start=start, end=end)
    return body, a0, a1

def transform(to_convert, decode_mode, name_dict={}, varname_dict=None,
              tokens=None, ret=True):
    if varname_dict is None:
        varname_dict = {}
    if tokens is None:
        tokens = []
        iterator = TokenParser(bytes(to_convert).decode("utf-8").splitlines(keepends=True))
    else:
        iterator = TokenParser(to_convert)
    def get_next():
        try:
            return next(iterator)
        except StopIteration:
            return dummy
    pos = 0
    for token in iterator:
        if iterator.idx - pos > 1:
            iterator.idx = pos + 1
            token = iterator.iterator[pos]
        pos = iterator.idx
        if token == dummy:
            continue
        tokens.append(token)
        if token.string == 'def':
            s0, s1 = token.start
            if (iterator.idx != 1 and iterator.iterator[iterator.idx-2].end[0] == s0
                    or (token := get_next()).type is not tokenize.NAME):
                _warn(token)
                continue
            name = token.string
            if get_next().string != '!':
                continue
            if (token := get_next()).string != '(':
                _warn(token)
                continue
            params = iterator.params() or ([], {}, [], {}, None, [], {}, None)
            if ((token := get_next()).string != ')'
                    or (token := get_next()).string != ':'):
                _warn(token)
                continue
            tokens.pop()
            token = get_next()
            if token.type is tokenize.INDENT:
                d0, d1 = token.start
                e0, e1 = token.end
                d1 = d1 if d1 and e0 <= d0 else 0
                body = [token._replace(start=(0, 0), end=(e0-d0, e1-d1))]
                while (token := get_next()).type is not tokenize.DEDENT:
                    s0, s1 = token.start
                    e0, e1 = token.end
                    d1 = d1 if d1 and e0 <= d0 else 0
                    body.append(token._replace(start=(s0-d0, s1-d1), end=(e0-d0, e1-d1)))
            else:
                if token.string.isspace() and token.type not in insertable_spaces:
                    token = get_next()
                d1 = token.start[1]
                body = [token._replace(start=(0, 0), end=(0, token.end[1]-d1))]
                while (token := get_next()).type is not tokenize.NEWLINE:
                    body.append(token._replace(
                        start=(0, token.start[1]-d1),
                        end=(0, token.end[1]-d1)
                    ))
            a0, a1 = iterator.iterator[iterator.idx].start
            a0 -= s0
            a1 -= s1
            add_offset(iterator.iterator, -a0, -a1, False, iterator.idx)
            name_dict[name] = (params, body)
        elif token.type is tokenize.NAME:
            if (token2 := get_next()).string != '!':
                continue
            start = token.start
            if token.string not in name_dict or (token2 := get_next()).string != '(':
                _warn(token2)
                continue
            tokens.pop()
            (poparams, podefaults, params, defaults, vpargs,
                koparams, kodefaults, vkwargs), body = name_dict[token.string]
            pargs, kwargs = iterator.args() or ([], {})
            end = get_next().end
            len_pargs, len_poparams = len(pargs), len(poparams)
            if not len_poparams:
                scope_vars = {}
            elif (len_pargs := len(pargs)) > (len_poparams := len(poparams)):
                len_pargs -= len_poparams
                scope_vars = dict(zip(poparams, pargs))
                pargs = pargs[len_poparams:]
            else:
                scope_vars = dict(zip(poparams, pargs))
                if len_pargs < len_poparams:
                    poparams = poparams[:]
                    len_poparams = _transfer(scope_vars, podefaults,
                                             poparams, len_pargs,
                                             len_poparams)
                    if len_poparams != len_pargs:
                        _warn(message=
                            "(warning) unaccounted positional-only "
                            "parameters; using name as string instead"
                        )
                        for i in range(len_pargs, len_poparams):
                            scope_vars[param := poparams[i]] = tokenize.TokenInfo(
                                tokenize.STRING, param, (0, 0), (0, len(param)), param
                            )
                len_pargs = 0
            len_params = len(params)
            if len_pargs:
                if len_pargs > len_params:
                    len_pargs -= len_params
                    scope_vars |= zip(params, pargs)
                    if vpargs is None:
                        _warn(message="(warning) unaccounted arguments")
                    else:
                        scope_vars[vpargs] = pargs[len_args:]
                    len_params = 0
                else:
                    len_params -= len_pargs
                    scope_vars |= zip(params, pargs)
                    params = params[len_pargs:]
                    len_pargs = 0
            if kwargs:
                if len_params:
                    params = params[:]
                    kwargs = kwargs[:]
                    len_params = _transfer(scope_vars, kwargs, params,
                                           stop=len_params, del_sdict_item=True)
                if kwargs and (len_koparams := len(koparams)):
                    koparams = koparams[:]
                    len_koparams = _transfer(scope_vars, kwargs, koparams,
                                             stop=len_koparams, del_sdict_item=True)
                    if len_koparams:
                        len_koparams = _transfer(scope_vars, kodefaults, koparams,
                                                 stop=len_koparams)
                        if len_koparams:
                            _warn(message=
                                "(warning) unaccounted keyword-only "
                                "parameters; using name as string instead"
                            )
                            for i in range(len_pargs, len_koparams):
                                scope_vars[param := koparams[i]] = tokenize.TokenInfo(
                                    tokenize.STRING, param, (0, 0), (0, len(param)), param
                                )
                if kwargs:
                    if vkwargs is None:
                        _warn(message="(warning) unaccounted keyword arguments")
                    else:
                        scope_vars[vkwargs] = kwargs
            else:
                params = params[:]
            if len_params:
                len_params = _transfer(scope_vars, defaults, params, stop=len_params)
                if len_params:
                    _warn(message=
                        "(warning) unaccounted parameters; "
                        "using name as string instead"
                    )
                    for i in range(len_pargs, len_params):
                        scope_vars[param := params[i]] = tokenize.TokenInfo(
                            tokenize.STRING, param, (0, 0), (0, len(param)), param
                        )
            body, a0, a1 = add_offset(body, *start)
            name_dict_ = name_dict.copy()
            body = transform(body, None, name_dict_, scope_vars, tokens, ret=False)
            e0, e1 = body[-1].end
            add_offset(iterator.iterator, e0-end[0], e1-end[1],
                       copy=False, start=iterator.idx)
        elif token.string == '$':
            start = token.start
            if (token := get_next()).type is not tokenize.NAME:
                _warn(token, message=
                    "(warning) unexpected token: {!r}; ignoring $"
                )
                tokens.pop()
                continue
            end = token.end
            tokens.pop()
            if (name := token.string) not in varname_dict:
                _warn(token, message=
                    "(warning) param ref does not match any known value: "
                    "{!r}; using ref name as string instead"
                )
                tok = tokenize.TokenInfo(
                    tokenize.STRING, name, start,
                    (end[0], a1:=start[1]+len(name)), name
                )
                l = None
                a0 = 0
                a1 -= end[1]
            else:
                s0, s1 = iterator.iterator[iterator.idx].start
                a0 = s0 - end[0]
                a1 = s1 - end[1]
                l = varname_dict[name]
                d0, d1 = l[0].start
                l, _, _ = add_offset(l, start[0] - d0, start[1] - d1)
                e0, e1 = l[-1].end
                a0 += e0 - s0
                a1 += e1 - s1
            add_offset(iterator.iterator, a0, a1, copy=False, start=iterator.idx)
            if l:
                for tok in reversed(l):
                    iterator.iterator.insert(iterator.idx, tok)
            else:
                iterator.iterator.insert(iterator.idx, tok)
        else:
            continue
        pos = iterator.idx
    if ret:
        t = tokens[-2]
        if t.type is tokenize.DEDENT:
            t, t2 = tokens[-3], tokens[-4]
            i = -3
        else:
            t2 = tokens[-3]
            i = -2
        if t2.end > t.start:
            s0, s1 = t2.end
            a0, a1 = t.end
            a0 -= t.start[0]
            a1 -= t.start[1]
            tokens[i] = t._replace(
                start=(s0, s1),
                end=(s0+a0, s1+a1)
            )
        #print(*tokens, sep='\n')
        return tokenize.untokenize(tokens)
    return tokens


decoder = functools.partial(transform, decode_mode=True)
encoder = functools.partial(transform, decode_mode=False)


class IncrementalDecoder(encodings.utf_8.IncrementalDecoder):
    def decode(self, string, final=False):
        self.buffer += string
        if final:
            buffer = self.buffer
            self.buffer = b""
            return super().decode(encoder(buffer))
        return ""


def macros_codec(encoding):
    if encoding == "macros":
        return codecs.CodecInfo(
            name="macros",
            encode=encodings.utf_8.encode,
            decode=decoder,
            incrementaldecoder=IncrementalDecoder,
        )

codecs.register(macros_codec)

-- Reconcile two observations of the same kills without charging or reading memory.
-- Native weapon counters retain coverage; target-bound observations fill their gaps.
return function(traits)
    traits=traits or {}
    local api={revision=0,policy='per_source_native_observed_max'}
    local native,observed,elements,anonymous,moved={},{},{fire={},poison={}},{fire=0,poison=0},{}
    local function count(v)return type(v)=='number'and v>=0 and v<=2147483647 and v%1==0 end
    local function hash(v)return type(v)=='string'and #v==16 and not v:find('[^%x]')and v~='0000000000000000'and v:upper()end
    function api:reset()
        native,observed,elements,anonymous,moved={},{},{fire={},poison={}},{fire=0,poison=0},{}
        self.revision=self.revision+1
    end
    function api:native(id,n,baseline)
        id=hash(id);if not id or not count(n)then return false end
        native[id]=baseline and n or (native[id]or 0)+n
        self.revision=self.revision+1;return true
    end
    function api:observe_source(id,raw,unknown_raw)
        id=hash(id);if not id then return false end
        raw=hash(raw)
        if raw and raw~=id then moved[raw]=(moved[raw]or 0)+1
        elseif not raw and unknown_raw==true then
            -- A missing raw owner is not a resource hash. Retain only a
            -- correction allowance for an excess unknown display pool.
            moved._unknown=(moved._unknown or 0)+1
        end
        observed[id]=(observed[id]or 0)+1;self.revision=self.revision+1;return true
    end
    function api:reassignments()
        local out={};for id,n in pairs(moved)do out[id]=n end;return out
    end
    function api:observe_element(element,id)
        if not elements[element]then return false end
        id=hash(id)
        if id then elements[element][id]=(elements[element][id]or 0)+1
        else anonymous[element]=anonymous[element]+1 end
        self.revision=self.revision+1;return true
    end
    function api:weapon(id)
        id=hash(id);return id and math.max(native[id]or 0,observed[id]or 0)or 0
    end
    function api:element(element)
        if not elements[element]then return 0 end
        local value=anonymous[element]
        local keys={};for id in pairs(native)do keys[id]=true end
        for id in pairs(elements[element])do keys[id]=true end
        for id in pairs(keys)do
            local trait=traits[id]or {}
            local flag=trait['native_'..element]
            if flag==nil then flag=trait[element]end
            value=value+math.max(flag==true and(native[id]or 0)or 0,elements[element][id]or 0)
        end
        return value
    end
    return api
end

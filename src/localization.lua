-- Display-only translation. Canonical names, persisted records and IDs never change.
return function(catalog)
    catalog=catalog or {}
    local exact=catalog.exact or {}
    local trie={}
    for source,target in pairs(catalog.fragments or {})do
        if type(source)=='string'and #source>0 and type(target)=='string'then
            local node=trie
            for i=1,#source do local byte=source:byte(i);node[byte]=node[byte]or{};node=node[byte]end
            node.value=target
        end
    end
    local cache,cache_size={},0
    local api={language='en',revision=0,code=nil}
    function api:set_language(code)
        self.code=code
        local normalized=type(code)=='string'and code:lower():gsub('_','-')or''
        local language=(normalized=='cn'or normalized=='tc'or normalized=='zh-cn'or normalized=='zh-tw'
            or normalized=='zh-hans'or normalized=='zh-hant'or normalized=='zh-hk')and'zh'or'en'
        if language==self.language then return false end
        self.language=language;self.revision=self.revision+1
        return true
    end
    local function english(value)
        if type(value)~='string'then return value end
        if exact[value]then return exact[value]end
        if cache[value]then return cache[value]end
        local result=value
        for _,rule in ipairs(catalog.patterns or{})do
            local count
            result,count=result:gsub(rule.source,rule.target)
            if count>0 then break end
        end
        local out,i={},1
        while i<=#result do
            local node,j,best,ending=trie,i,nil,nil
            while j<=#result and node[result:byte(j)]do
                node=node[result:byte(j)];j=j+1
                if node.value then best,ending=node.value,j end
            end
            if best then out[#out+1]=best;i=ending
            else out[#out+1]=result:sub(i,i);i=i+1 end
        end
        result=table.concat(out)
        if cache_size>=2048 then cache={};cache_size=0 end
        cache[value]=result;cache_size=cache_size+1
        return result
    end
    function api:text(value)return self.language=='zh'and value or english(value)end
    -- Search aliases use English even while Chinese is selected; player names
    -- continue to match their raw values in the query layer.
    function api:english(value)return english(value)end
    local next_poll=0
    function api:poll(runtime,now,reader)
        if type(now)~='number'or now<next_poll or type(reader)~='function'then return false end
        next_poll=now+1
        local ok,code=pcall(reader,runtime)
        if not ok or type(code)~='string'then return false end
        return self:set_language(code)
    end
    return api
end

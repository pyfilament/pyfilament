import { ApolloClient, HttpLink, InMemoryCache } from '@apollo/client';
import { ApolloProvider } from '@apollo/client/react';
import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const ApolloContext = ({ children }) => {
    const client = React.useMemo(() => {
        return new ApolloClient({
            cache: new InMemoryCache(),
            link: new HttpLink({
                uri: '/graphql',
            }),
        });
    });

    const location = useLocation();

    useEffect(() => {
        if (client) {
            client.cache.restore();
        }
    }, [location, client]);

    return <ApolloProvider client={client}>{children}</ApolloProvider>;
};

export default ApolloContext;
